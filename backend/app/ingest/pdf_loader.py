"""PDF loader (pdfplumber).

Extracts page text and tables with `[page N]` markers (so the model can cite a
location). If a PDF yields almost no text it is likely scanned — we flag that
clearly rather than pretending it was empty.
"""
from __future__ import annotations

from pathlib import Path

from .loaders import ExtractedDoc

_SCANNED_THRESHOLD = 40  # chars; below this a PDF is probably image-only


def load_pdf(path: Path) -> ExtractedDoc:
    import pdfplumber

    parts: list[str] = []
    warnings: list[str] = []
    page_count = 0
    with pdfplumber.open(str(path)) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            parts.append(f"[page {i}]")
            txt = page.extract_text() or ""
            if txt.strip():
                parts.append(txt)
            # Pull simple tables so spreadsheet-like content in PDFs is captured.
            for table in page.extract_tables() or []:
                for row in table:
                    cells = [c for c in row if c]
                    if cells:
                        parts.append(" | ".join(str(c) for c in cells))

    text = "\n".join(parts).strip()
    if len(text.replace("[page 1]", "").strip()) < _SCANNED_THRESHOLD:
        warnings.append(
            "PDF yielded little/no text — it is likely a scanned image. "
            "Provide it as an image file for vision/OCR, or install OCR support."
        )
    return ExtractedDoc(
        name=path.name,
        path=str(path),
        media_type="pdf",
        text=text,
        pages=page_count or 1,
        ingest_method="pdfplumber",
        warnings=warnings,
    )
