"""Reconcile the model's analysis against the actual inventory.

Converts the LLM mappings/gaps into domain objects, flags required systems that
are absent from the inventory (a different class of gap), assigns stable gap ids,
and records which use cases each missing integration blocks.
"""
from __future__ import annotations

import re

from ..schemas.gaps import (
    DataFlow,
    GapStatus,
    IntegrationGap,
    LLMGapAnalysis,
    UseCaseInput,
    UseCaseMapping,
)
from ..schemas.inventory import Inventory


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def reconcile(analysis: LLMGapAnalysis, inv: Inventory,
              use_cases: list[UseCaseInput]) -> tuple[list[UseCaseMapping], list[IntegrationGap]]:
    inv_names = {_norm(s.name) for s in inv.systems}
    uc_by_id = {uc.id: uc for uc in use_cases}

    mappings: list[UseCaseMapping] = []
    for m in analysis.mappings:
        uc = uc_by_id.get(m.use_case_id)
        missing = [s for s in m.required_systems if _norm(s) not in inv_names]
        mappings.append(UseCaseMapping(
            use_case_id=m.use_case_id,
            name=uc.name if uc else m.use_case_id,
            required_systems=m.required_systems,
            missing_systems=missing,
            data_flows=[DataFlow(source_system=f.source_system,
                                 destination_system=f.destination_system,
                                 entity=f.entity, trigger=f.trigger)
                        for f in m.data_flows],
            rationale=m.rationale,
        ))

    gaps: list[IntegrationGap] = []
    for i, g in enumerate(analysis.gaps, start=1):
        valid_ucs = [uid for uid in g.required_by_use_case_ids if uid in uc_by_id]
        blocks = valid_ucs if g.status == GapStatus.missing else []
        gaps.append(IntegrationGap(
            id=f"gap-{i}",
            source_system=g.source_system,
            destination_system=g.destination_system,
            integration_name=g.integration_name or f"{g.source_system} -> {g.destination_system}",
            description=g.description,
            status=g.status,
            effort_level=g.effort_level,
            effort_days=g.effort_days,
            effort_rationale=g.effort_rationale,
            required_by_use_cases=valid_ucs,
            blocks_use_cases=blocks,
        ))
    return mappings, gaps
