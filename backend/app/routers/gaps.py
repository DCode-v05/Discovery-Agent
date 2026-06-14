"""Level 2 API — use-case mapping & integration gap analysis."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import PROJECT_ROOT
from ..gapanalysis.service import load_use_cases, run_gap_analysis, to_markdown
from ..llm.errors import LLMError
from ..observability import RunLedger
from ..schemas.gaps import UseCaseInput
from ..schemas.inventory import Inventory

router = APIRouter(prefix="/gaps", tags=["gaps"])

_DEFAULT_USE_CASES = PROJECT_ROOT / "data" / "use_cases.json"


class GapRequest(BaseModel):
    inventory: Inventory
    use_cases: list[UseCaseInput] | None = None
    use_cases_path: str | None = None


@router.post("/run")
def run(req: GapRequest) -> dict:
    use_cases = req.use_cases
    if not use_cases:
        path = Path(req.use_cases_path) if req.use_cases_path else _DEFAULT_USE_CASES
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"use_cases not found: {path}")
        use_cases = load_use_cases(path)

    ledger = RunLedger(kind="gaps")
    try:
        report = run_gap_analysis(req.inventory, use_cases, ledger=ledger)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=exc.as_dict()) from exc

    out_dir = PROJECT_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "gaps.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")

    return {"run_id": ledger.run_id, "report": report.model_dump(mode="json"),
            "markdown": to_markdown(report)}
