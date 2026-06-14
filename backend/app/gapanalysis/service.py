"""Level 2 orchestration: inventory + use cases -> prioritized gap report."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..llm.router import LLMRouter
from ..observability import RunLedger
from ..schemas.gaps import GapReport, GapStatus, Priority, UseCaseInput
from ..schemas.inventory import Inventory
from .gap_detector import reconcile
from .mapper import analyze
from .prioritizer import prioritize


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_inventory(path: str | Path) -> Inventory:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Inventory.model_validate(data)


def load_use_cases(path: str | Path) -> list[UseCaseInput]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "use_cases" in data:
        data = data["use_cases"]
    return [UseCaseInput.model_validate(uc) for uc in data]


def run_gap_analysis(inv: Inventory, use_cases: list[UseCaseInput],
                     ledger: RunLedger | None = None,
                     router: LLMRouter | None = None) -> GapReport:
    ledger = ledger or RunLedger(kind="gaps")
    router = router or LLMRouter(ledger=ledger)

    analysis = analyze(inv, use_cases, router, ledger)
    mappings, gaps = reconcile(analysis, inv, use_cases)
    gaps, statements = prioritize(gaps, use_cases, ledger)

    missing = sum(1 for g in gaps if g.status == GapStatus.missing)
    summary = (
        f"{len(use_cases)} use cases mapped across {inv.systems_count} systems. "
        f"{missing} of {len(gaps)} required integrations are missing; "
        f"{sum(1 for g in gaps if g.priority == Priority.critical)} are critical priority."
    )
    report = GapReport(
        run_id=ledger.run_id,
        generated_at=_now(),
        use_case_count=len(use_cases),
        gap_count=len(gaps),
        mappings=mappings,
        gaps=gaps,
        dependency_statements=statements,
        summary=summary,
        warnings=[f"Use case '{m.name}' needs system(s) not in inventory: "
                  + ", ".join(m.missing_systems) for m in mappings if m.missing_systems],
    )
    ledger.finish(use_cases=len(use_cases), gaps=len(gaps), missing=missing)
    return report


# --------------------------------------------------------------------------- #
def to_markdown(report: GapReport) -> str:
    lines = [
        "# Integration Gap Analysis",
        "",
        f"- **Run:** `{report.run_id}`",
        f"- **Generated:** {report.generated_at}",
        f"- **Summary:** {report.summary}",
        "",
        "## Prioritized integration gaps",
        "",
        "| Priority | Integration | Status | Effort | Impact | Blocks |",
        "|---|---|---|---|---|---|",
    ]
    for g in report.gaps:
        lines.append(
            f"| {g.priority.value} | {g.integration_name} | {g.status.value} "
            f"| {g.effort_level.value} (~{g.effort_days}d) | {g.business_impact_score} "
            f"| {len(g.blocks_use_cases)} |"
        )
    lines += ["", "## Use-case mappings", ""]
    for m in report.mappings:
        lines.append(f"### {m.name} ({m.use_case_id})")
        lines.append(f"- **Systems:** {', '.join(m.required_systems) or 'n/a'}")
        if m.missing_systems:
            lines.append(f"- **⚠ Missing from inventory:** {', '.join(m.missing_systems)}")
        for f in m.data_flows:
            lines.append(f"    - {f.source_system} → {f.destination_system} "
                         f"[{f.entity}] on _{f.trigger}_")
        lines.append("")
    if report.dependency_statements:
        lines += ["## Dependencies", ""] + [f"- {s}" for s in report.dependency_statements]
    return "\n".join(lines)
