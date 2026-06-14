"""Level 1 API — systems discovery from uploaded files or a server-side path."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..config import PROJECT_ROOT
from ..discovery.service import run_discovery, to_markdown
from ..llm.errors import LLMError
from ..observability import RunLedger

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _resolve_source(files: list[UploadFile] | None, path: str | None) -> Path:
    if files:
        tmpdir = Path(tempfile.mkdtemp(prefix="disco_"))
        for f in files:
            if not f.filename:
                continue
            dest = tmpdir / Path(f.filename).name
            with dest.open("wb") as out:
                shutil.copyfileobj(f.file, out)
        return tmpdir
    if path:
        src = Path(path)
        if not src.is_absolute():
            src = PROJECT_ROOT / path
        if not src.exists():
            raise HTTPException(status_code=400, detail=f"path not found: {src}")
        return src
    raise HTTPException(status_code=400, detail="Provide files to upload or a server-side path.")


@router.post("/run")
async def run(
    files: list[UploadFile] | None = File(default=None),
    path: str | None = Form(default=None),
) -> dict:
    source = _resolve_source(files, path)
    ledger = RunLedger(kind="discovery")
    try:
        inv = run_discovery(source, ledger=ledger)
    except LLMError as exc:
        # Clear, actionable failure (e.g. missing key) rather than a 500.
        raise HTTPException(status_code=502, detail=exc.as_dict()) from exc

    out_dir = PROJECT_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "inventory.json").write_text(inv.model_dump_json(indent=2), encoding="utf-8")

    return {"run_id": ledger.run_id, "inventory": inv.model_dump(mode="json"),
            "markdown": to_markdown(inv)}
