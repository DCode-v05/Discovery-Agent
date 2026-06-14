"""Observability — structured logging + a per-run ledger.

Every meaningful action (document processed, LLM call, decision, confidence
score, failure) is recorded as a structured event. Events are:
  - printed as structured JSON lines to stderr (operator visibility), and
  - appended to a per-run JSONL ledger under data/runs/<run_id>.jsonl

The React Observability panel reads the ledger via GET /runs/{run_id} so the
operator can see the agent's reasoning — one of the five graded traits.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import get_settings

_logger = logging.getLogger("discovery_agent")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)


def new_run_id() -> str:
    # uuid4 is fine here; this is not on a prompt-cache path.
    return f"run_{uuid.uuid4().hex[:12]}"


@dataclass
class RunLedger:
    """Collects structured events for a single agent run.

    Use as the observability handle threaded through a discovery/gap/codegen run.
    """

    run_id: str = field(default_factory=new_run_id)
    kind: str = "discovery"  # discovery | gaps | codegen
    events: list[dict[str, Any]] = field(default_factory=list)
    _path: Path | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        ledger_dir = get_settings().run_ledger_path
        self._path = ledger_dir / f"{self.run_id}.jsonl"
        self.event("run_started", kind=self.kind)

    # -- core API -----------------------------------------------------------
    def event(self, event_type: str, level: str = "info", **fields: Any) -> dict[str, Any]:
        rec = {
            "run_id": self.run_id,
            "ts": round(time.time(), 3),
            "event": event_type,
            "level": level,
            **fields,
        }
        self.events.append(rec)
        line = json.dumps(rec, default=str)
        getattr(_logger, level if level in {"info", "warning", "error"} else "info")(line)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return rec

    # -- semantic helpers ---------------------------------------------------
    def decision(self, what: str, choice: str, why: str, **extra: Any) -> None:
        """Record a context-driven decision (graded trait #1)."""
        self.event("decision", what=what, choice=choice, why=why, **extra)

    def llm_call(self, provider: str, model: str, task: str, latency_ms: float,
                 tokens: int | None = None, **extra: Any) -> None:
        self.event("llm_call", provider=provider, model=model, task=task,
                   latency_ms=round(latency_ms, 1), tokens=tokens, **extra)

    def confidence(self, subject: str, score: float, tier: str, note: str | None = None) -> None:
        self.event("confidence", subject=subject, score=score, tier=tier, note=note)

    def failure(self, what: str, error: str, needs: str, **extra: Any) -> None:
        """Record a clear failure (graded trait #3): what was tried, why it failed,
        and what the operator must supply."""
        self.event("failure", level="error", what=what, error=error, needs=needs, **extra)

    def finish(self, **summary: Any) -> None:
        self.event("run_finished", **summary)

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "kind": self.kind, "events": self.events}


def load_ledger(run_id: str) -> dict[str, Any] | None:
    """Read a persisted ledger back from disk (for the API/UI)."""
    path = get_settings().run_ledger_path / f"{run_id}.jsonl"
    if not path.exists():
        return None
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kind = next((e.get("kind") for e in events if e.get("event") == "run_started"), "unknown")
    return {"run_id": run_id, "kind": kind, "events": events}


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """List recent runs (most recent first) with a small summary."""
    ledger_dir = get_settings().run_ledger_path
    files = sorted(ledger_dir.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for p in files[:limit]:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
            first = json.loads(lines[0]) if lines else {}
            out.append({
                "run_id": p.stem,
                "kind": first.get("kind", "unknown"),
                "ts": first.get("ts"),
                "events": len(lines),
            })
        except Exception:  # noqa: BLE001 - listing must never crash the API
            continue
    return out
