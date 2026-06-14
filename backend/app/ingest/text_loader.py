"""Plain-text and Markdown loader."""
from __future__ import annotations

from pathlib import Path

from .loaders import ExtractedDoc


def load_text(path: Path, media_type: str) -> ExtractedDoc:
    text = path.read_text(encoding="utf-8", errors="replace")
    warnings: list[str] = []
    if not text.strip():
        warnings.append("Document is empty.")
    return ExtractedDoc(
        name=path.name,
        path=str(path),
        media_type=media_type,
        text=text,
        pages=1,
        ingest_method="raw",
        warnings=warnings,
    )
