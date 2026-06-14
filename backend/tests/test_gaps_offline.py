"""Offline tests for the Level 2 pipeline (reconcile + prioritizer).

A fake router returns a fixed analysis so we can verify gap reconciliation,
missing-system detection, business-impact scoring, priority buckets, and
dependency statements deterministically — no API keys.
"""
from __future__ import annotations

from backend.app.config import PROJECT_ROOT
from backend.app.gapanalysis.service import load_use_cases, run_gap_analysis, to_markdown
from backend.app.schemas.gaps import (
    GapStatus,
    LLMDataFlow,
    LLMGap,
    LLMGapAnalysis,
    LLMUseCaseMapping,
    Priority,
)
from backend.app.schemas.inventory import (
    ConfidenceTier,
    Criticality,
    Inventory,
    System,
)

INVENTORY_SYSTEMS = ["Salesforce", "NetSuite", "Coupa", "Snowflake", "Stripe", "Workday", "Okta"]


def _inventory() -> Inventory:
    systems = [
        System(name=n, category="x", auth_method="x", confidence=0.95,
               confidence_tier=ConfidenceTier.explicit, criticality=Criticality.high)
        for n in INVENTORY_SYSTEMS
    ]
    return Inventory(run_id="t", generated_at="t", document_count=5,
                     systems_count=len(systems), systems=systems)


class FakeRouter:
    def structured(self, *, task, schema, prompt, system="", images=None, model=None):
        return LLMGapAnalysis(
            mappings=[
                LLMUseCaseMapping(use_case_id="uc1", required_systems=["Salesforce", "NetSuite"],
                                  data_flows=[LLMDataFlow(source_system="Salesforce", destination_system="NetSuite", entity="Order", trigger="Closed-Won")]),
                LLMUseCaseMapping(use_case_id="uc2", required_systems=["Coupa", "NetSuite"],
                                  data_flows=[LLMDataFlow(source_system="Coupa", destination_system="NetSuite", entity="PO", trigger="PO approved")]),
                LLMUseCaseMapping(use_case_id="uc3", required_systems=["Workday", "Okta", "Salesforce"],
                                  data_flows=[]),
                LLMUseCaseMapping(use_case_id="uc4", required_systems=["NetSuite", "Stripe", "Snowflake"],
                                  data_flows=[]),
                LLMUseCaseMapping(use_case_id="uc5", required_systems=["Zendesk", "Salesforce"],
                                  data_flows=[]),  # Zendesk NOT in inventory
                LLMUseCaseMapping(use_case_id="uc6", required_systems=["marketing automation platform", "Salesforce"],
                                  data_flows=[]),  # not in inventory
            ],
            gaps=[
                LLMGap(source_system="Salesforce", destination_system="NetSuite",
                       integration_name="Salesforce -> NetSuite", description="orders",
                       status=GapStatus.available, effort_level="low", effort_days=0,
                       required_by_use_case_ids=["uc1"]),
                LLMGap(source_system="Coupa", destination_system="NetSuite",
                       integration_name="Coupa -> NetSuite", description="bills",
                       status=GapStatus.missing, effort_level="medium", effort_days=10,
                       required_by_use_case_ids=["uc2"]),
                LLMGap(source_system="Okta", destination_system="Salesforce",
                       integration_name="Okta -> Salesforce", description="provisioning",
                       status=GapStatus.missing, effort_level="medium", effort_days=8,
                       required_by_use_case_ids=["uc3"]),
                LLMGap(source_system="NetSuite", destination_system="Snowflake",
                       integration_name="NetSuite -> Snowflake", description="finance load",
                       status=GapStatus.missing, effort_level="high", effort_days=15,
                       required_by_use_case_ids=["uc4"]),
                LLMGap(source_system="Zendesk", destination_system="Salesforce",
                       integration_name="Zendesk -> Salesforce", description="tickets",
                       status=GapStatus.missing, effort_level="medium", effort_days=9,
                       required_by_use_case_ids=["uc5"]),
                LLMGap(source_system="marketing automation platform", destination_system="Salesforce",
                       integration_name="Marketing -> Salesforce", description="lead routing",
                       status=GapStatus.missing, effort_level="medium", effort_days=7,
                       required_by_use_case_ids=["uc6"]),
            ],
        )

    def text(self, **_):
        return ""


def test_gap_analysis_reconciles_scores_and_orders():
    inv = _inventory()
    use_cases = load_use_cases(PROJECT_ROOT / "data" / "use_cases.json")
    report = run_gap_analysis(inv, use_cases, router=FakeRouter())

    # >= 5 use cases mapped
    assert report.use_case_count == 6
    assert len(report.mappings) >= 5

    m_by_id = {m.use_case_id: m for m in report.mappings}
    # missing-system detection
    assert "Zendesk" in m_by_id["uc5"].missing_systems
    assert any("marketing" in s.lower() for s in m_by_id["uc6"].missing_systems)

    g_by_name = {g.integration_name: g for g in report.gaps}
    # existing integration is 'available' and low priority
    assert g_by_name["Salesforce -> NetSuite"].status == GapStatus.available
    assert g_by_name["Salesforce -> NetSuite"].priority == Priority.low

    # highest-frequency use case (uc6, 15000/yr) yields the top-impact missing gap
    missing = [g for g in report.gaps if g.status == GapStatus.missing]
    assert missing[0].business_impact_score == max(g.business_impact_score for g in missing)
    assert any(g.priority == Priority.critical for g in missing)

    # missing gaps sort before available
    statuses = [g.status for g in report.gaps]
    assert statuses.index(GapStatus.missing) < statuses.index(GapStatus.available)

    # dependency statements exist and are well-formed
    assert report.dependency_statements
    assert all("must exist before" in s for s in report.dependency_statements)

    # report renders
    md = to_markdown(report)
    assert "Integration Gap Analysis" in md and "Dependencies" in md
