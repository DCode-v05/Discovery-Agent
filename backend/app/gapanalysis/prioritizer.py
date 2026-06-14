"""Deterministic prioritization & dependency mapping.

Priority is computed in code (not asked of the model) so the ranking is
explainable and reproducible. Business impact combines:
  * how often the blocked workflows run (frequency),
  * how business-critical they are (criticality), and
  * how many use cases the gap blocks (downstream leverage).

`business_impact_score = max_over_requiring_use_cases(freq_norm * crit_weight)
                         * (1 + 0.5 * (blocks_count - 1))`

Priority buckets are assigned by each gap's score relative to the run's maximum,
so the highest-leverage gap is always surfaced first.
"""
from __future__ import annotations

from ..observability import RunLedger
from ..schemas.gaps import (
    GapStatus,
    IntegrationGap,
    Priority,
    UseCaseInput,
)

_CRIT_WEIGHT = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}


def _crit_weight(value: str) -> float:
    return _CRIT_WEIGHT.get((value or "medium").lower(), 2.0)


def prioritize(gaps: list[IntegrationGap], use_cases: list[UseCaseInput],
               ledger: RunLedger | None = None) -> tuple[list[IntegrationGap], list[str]]:
    uc_by_id = {uc.id: uc for uc in use_cases}
    max_freq = max((uc.frequency_per_year for uc in use_cases), default=1) or 1

    # 1. raw business-impact score per gap
    for g in gaps:
        requiring = [uc_by_id[u] for u in g.required_by_use_cases if u in uc_by_id]
        if requiring:
            base = max((uc.frequency_per_year / max_freq) * _crit_weight(uc.criticality)
                       for uc in requiring)
        else:
            base = 0.0
        blocks_count = len(g.blocks_use_cases)
        leverage = 1 + 0.5 * (blocks_count - 1) if blocks_count > 0 else 1.0
        g.business_impact_score = round(base * leverage, 3)

    # 2. priority buckets relative to the strongest gap
    max_score = max((g.business_impact_score for g in gaps), default=0.0) or 1.0
    for g in gaps:
        ratio = g.business_impact_score / max_score
        if g.status == GapStatus.available:
            g.priority = Priority.low  # already exists — nothing to build
        elif ratio >= 0.75:
            g.priority = Priority.critical
        elif ratio >= 0.5:
            g.priority = Priority.high
        elif ratio >= 0.25:
            g.priority = Priority.medium
        else:
            g.priority = Priority.low

    # 3. dependency notes + report-level dependency statements
    statements: list[str] = []
    for g in gaps:
        if g.status == GapStatus.missing and g.blocks_use_cases:
            names = [uc_by_id[u].name for u in g.blocks_use_cases if u in uc_by_id]
            g.dependency_note = (
                f"Integration '{g.integration_name}' must exist before: " + ", ".join(names) + "."
            )
            for n in names:
                statements.append(
                    f"Integration '{g.integration_name}' must exist before use case '{n}' can be automated."
                )

    # 4. sort: missing first, then by impact desc
    gaps.sort(key=lambda g: (g.status == GapStatus.available, -g.business_impact_score))
    if ledger:
        ledger.event("prioritized", gaps=len(gaps),
                     critical=sum(1 for g in gaps if g.priority == Priority.critical),
                     statements=len(statements))
    return gaps, statements
