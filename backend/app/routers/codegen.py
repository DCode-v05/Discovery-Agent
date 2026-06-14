"""Level 3 API — integration & agent code generation + bundle download."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..codegen.service import generate_code, to_markdown
from ..config import PROJECT_ROOT
from ..llm.errors import LLMError
from ..observability import RunLedger
from ..schemas.gaps import GapReport, IntegrationGap

router = APIRouter(prefix="/codegen", tags=["codegen"])


class CodegenRequest(BaseModel):
    gaps: list[IntegrationGap] | None = None
    report: GapReport | None = None
    top_n: int = 3
    run_tests: bool = True


@router.post("/run")
def run(req: CodegenRequest) -> dict:
    gaps = req.gaps if req.gaps else (req.report.gaps if req.report else None)
    if not gaps:
        raise HTTPException(status_code=400, detail="Provide 'gaps' or a 'report' with gaps.")

    ledger = RunLedger(kind="codegen")
    try:
        result = generate_code(gaps, ledger=ledger, top_n=req.top_n, run_tests=req.run_tests)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=exc.as_dict()) from exc

    return {"run_id": ledger.run_id, "result": result.model_dump(mode="json"),
            "markdown": to_markdown(result),
            "bundle_url": f"/codegen/bundle/{ledger.run_id}" if result.bundle_path else None}


@router.get("/bundle/{run_id}")
def bundle(run_id: str) -> FileResponse:
    zip_path = PROJECT_ROOT / "out" / f"connectors_{run_id}.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="bundle not found")
    return FileResponse(str(zip_path), media_type="application/zip",
                        filename=f"connectors_{run_id}.zip")
