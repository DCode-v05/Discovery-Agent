"""Observability endpoints — expose the run ledger to the UI."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..observability import list_runs, load_ledger

router = APIRouter(prefix="/runs", tags=["observability"])


@router.get("")
def runs(limit: int = 50) -> list[dict]:
    return list_runs(limit=limit)


@router.get("/{run_id}")
def run(run_id: str) -> dict:
    ledger = load_ledger(run_id)
    if ledger is None:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
    return ledger
