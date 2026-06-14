"""Use-case -> system mapping and gap detection (LLM step).

Given the discovered inventory and a list of automation use cases, the model maps
each use case to the systems it needs, traces the data flows, and proposes the
integrations required (marking each available or missing). Evidence quotes from
Level 1 are included so the model can tell which integrations already exist.
"""
from __future__ import annotations

from ..llm.router import LLMRouter
from ..observability import RunLedger
from ..schemas.gaps import LLMGapAnalysis, UseCaseInput
from ..schemas.inventory import Inventory

GAP_SYSTEM = """You are a senior integration architect.
You are given (1) an inventory of systems an enterprise uses and (2) a list of
automation use cases. For each use case, determine which systems it requires and
the data flows between them, then identify the integrations needed.

RULES (graded):
- Use ONLY systems that appear in the provided inventory. If a use case clearly
  needs a system that is NOT in the inventory, still name it in required_systems
  (it will be flagged as a missing system) but do not invent its details.
- Mark an integration status 'available' ONLY if the inventory evidence indicates
  that integration already exists (e.g. an "existing integrations" note). Otherwise
  mark it 'missing'. Do not assume integrations exist.
- A data flow has a source system, a destination system, the entity that moves,
  and the trigger event.
- Give a rough order-of-magnitude effort (low/medium/high and a day estimate) for
  each MISSING integration.
- required_by_use_case_ids must reference the provided use-case ids."""


def _inventory_summary(inv: Inventory) -> str:
    lines = ["SYSTEM INVENTORY:"]
    for s in inv.systems:
        ev = "; ".join(e.quote.strip()[:120] for e in s.evidence[:2])
        lines.append(
            f"- {s.name} | category={s.category} | criticality={s.criticality.value} "
            f"| auth={s.auth_method} | entities={', '.join(s.key_entities) or 'n/a'}"
            + (f" | evidence: {ev}" if ev else "")
        )
    return "\n".join(lines)


def _use_cases_block(use_cases: list[UseCaseInput]) -> str:
    lines = ["AUTOMATION USE CASES:"]
    for uc in use_cases:
        lines.append(
            f"- id={uc.id} | {uc.name} | freq/yr={uc.frequency_per_year} "
            f"| criticality={uc.criticality}\n    {uc.description}"
        )
    return "\n".join(lines)


def analyze(inv: Inventory, use_cases: list[UseCaseInput], router: LLMRouter,
            ledger: RunLedger | None = None) -> LLMGapAnalysis:
    prompt = (
        _inventory_summary(inv) + "\n\n" + _use_cases_block(use_cases)
        + "\n\nMap every use case and identify all required integrations."
    )
    if ledger:
        ledger.event("gap_analysis_started", systems=inv.systems_count,
                     use_cases=len(use_cases))
    result = router.structured(task="gap_analysis", schema=LLMGapAnalysis,
                               prompt=prompt, system=GAP_SYSTEM)
    if not isinstance(result, LLMGapAnalysis):
        result = LLMGapAnalysis()
    if ledger:
        ledger.event("gap_analysis_raw", mappings=len(result.mappings),
                     gaps=len(result.gaps))
    return result
