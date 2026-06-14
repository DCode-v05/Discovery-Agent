"""Offline tests for the Level 1 pipeline.

Uses a fake LLM router so we can verify ingestion, merge, grounding (the
hallucination guard), and the confidence policy deterministically — no API keys.
Run: pytest backend/tests/test_discovery_offline.py -q
"""
from __future__ import annotations

import re

from backend.app.config import PROJECT_ROOT
from backend.app.discovery.service import run_discovery, to_markdown
from backend.app.ingest.loaders import discover_documents, load_document
from backend.app.schemas.inventory import DocumentExtraction, ExtractedSystem

KB = PROJECT_ROOT / "data" / "kb"

# Systems we expect the (faked) model to "see" in text documents, with a confidence.
KNOWN = {
    "Salesforce": 0.97, "NetSuite": 0.96, "Coupa": 0.95, "Snowflake": 0.95,
    "Okta": 0.95, "Workday": 0.93, "Stripe": 0.9, "Slack": 0.85, "Zendesk": 0.6,
}


def _window(text: str, name: str, span: int = 70) -> str:
    i = text.lower().find(name.lower())
    if i == -1:
        return name
    start = max(0, i - 10)
    return re.sub(r"\s+", " ", text[start : i + len(name) + span]).strip()


class FakeRouter:
    """Returns grounded extractions for known systems found in the prompt, plus a
    deliberately HALLUCINATED system on the architecture PDF to test the guard."""

    def structured(self, *, task, schema, prompt, system="", images=None, model=None):
        systems: list[ExtractedSystem] = []
        for name, conf in KNOWN.items():
            if name.lower() in prompt.lower():
                systems.append(ExtractedSystem(
                    name=name, category="Unknown", auth_method="Unknown",
                    key_entities=[], business_processes=[], criticality="unknown",
                    confidence=conf, evidence_quote=_window(prompt, name),
                    location="text", uncertainty_note="" if conf >= 0.7 else "passing mention",
                ))
        # Inject a hallucination only when the architecture PDF is the source.
        if "architecture_overview" in prompt or "Systems Architecture" in prompt:
            systems.append(ExtractedSystem(
                name="Initech Mainframe", category="ERP", auth_method="LDAP",
                key_entities=["Ledger"], business_processes=["Accounting"],
                criticality="high", confidence=0.92,
                evidence_quote="Initech Mainframe is our primary accounting system of record.",
                location="page 9", uncertainty_note="",
            ))
        return DocumentExtraction(systems=systems)

    def text(self, **_):  # unused here
        return ""


def test_loaders_read_all_sample_formats():
    paths = discover_documents(KB)
    assert len(paths) >= 5
    media = {load_document(p).media_type for p in paths}
    # pdf, image, spreadsheet, markdown, text all present
    assert {"pdf", "image", "spreadsheet", "markdown", "text"} <= media


def test_pipeline_extracts_grounds_and_flags():
    inv = run_discovery(KB, router=FakeRouter())

    names = {s.name for s in inv.systems}
    # >= 80% of strong systems discovered
    strong = {"Salesforce", "NetSuite", "Coupa", "Snowflake", "Okta", "Workday", "Stripe"}
    assert len(strong & names) >= 6

    by_name = {s.name: s for s in inv.systems}

    # Grounded, explicit, high-confidence
    sf = by_name["Salesforce"]
    assert sf.confidence_tier.value == "explicit"
    assert any(e.grounded for e in sf.evidence)
    assert not sf.needs_review

    # Passing mention -> review tier
    if "Zendesk" in by_name:
        assert by_name["Zendesk"].needs_review

    # HALLUCINATION GUARD: fabricated system is caught, capped, and flagged
    hall = by_name["Initech Mainframe"]
    assert hall.confidence <= 0.49
    assert hall.needs_review
    assert all(not e.grounded for e in hall.evidence)
    assert "hallucination" in (hall.uncertainty_note or "").lower()

    # Report renders
    md = to_markdown(inv)
    assert "System Discovery Report" in md and "Salesforce" in md
