"""Document ingestion — dispatch by file type and return a normalized `ExtractedDoc`.

Each loader produces:
  * `text` — the best available text layer (used for extraction AND grounding).
  * `images` — vision inputs (set for image documents / scanned pages).
The extractor decides per-document whether to use the text or the vision path.
Unsupported or unreadable files are reported (as `SkippedDocument`), never dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..llm.base import ImageInput

# file extension -> media type
PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
SHEET_EXTS = {".xlsx", ".xls", ".csv"}
MD_EXTS = {".md", ".markdown"}
TEXT_EXTS = {".txt", ".text", ".log"}

SUPPORTED_EXTS = PDF_EXTS | IMAGE_EXTS | SHEET_EXTS | MD_EXTS | TEXT_EXTS


@dataclass
class ExtractedDoc:
    name: str
    path: str
    media_type: str               # pdf | image | spreadsheet | markdown | text
    text: str = ""                # text layer (extraction + grounding reference)
    images: list[ImageInput] = field(default_factory=list)
    pages: int = 1
    ingest_method: str = "raw"    # pdfplumber | ocr | vision | pandas | raw
    warnings: list[str] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())

    @property
    def has_images(self) -> bool:
        return bool(self.images)


class UnsupportedDocument(Exception):
    def __init__(self, path: str, ext: str):
        super().__init__(f"Unsupported file type '{ext}' for {path}")
        self.path = path
        self.ext = ext
        self.needs = (
            f"Provide one of: PDF, image (PNG/JPG/WebP), spreadsheet (XLSX/CSV), "
            f"Markdown, or plain text. Got '{ext}'."
        )


def media_type_for(ext: str) -> str:
    ext = ext.lower()
    if ext in PDF_EXTS:
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in SHEET_EXTS:
        return "spreadsheet"
    if ext in MD_EXTS:
        return "markdown"
    if ext in TEXT_EXTS:
        return "text"
    return "unknown"


def load_document(path: str | Path) -> ExtractedDoc:
    """Load a single document. Raises UnsupportedDocument for unknown types and
    lets loader-specific exceptions propagate (the service records them clearly)."""
    p = Path(path)
    ext = p.suffix.lower()
    media = media_type_for(ext)

    if media == "pdf":
        from .pdf_loader import load_pdf
        return load_pdf(p)
    if media == "image":
        from .image_loader import load_image
        return load_image(p)
    if media == "spreadsheet":
        from .spreadsheet_loader import load_spreadsheet
        return load_spreadsheet(p)
    if media in {"markdown", "text"}:
        from .text_loader import load_text
        return load_text(p, media)
    raise UnsupportedDocument(str(p), ext or "(none)")


def discover_documents(directory: str | Path) -> list[Path]:
    """Return all supported document paths under a directory (sorted, non-recursive
    top level + one level of nesting is enough for the demo)."""
    d = Path(directory)
    if d.is_file():
        return [d]
    files = [p for p in sorted(d.rglob("*"))
             if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    return files
