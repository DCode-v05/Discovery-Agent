"""Image loader — vision-first with a local OCR (Tesseract) fallback for the text layer.

The raw image is always attached for the vision path (the extractor sends it to a
multimodal model). We ALSO try Tesseract OCR to produce a text layer that grounding
can verify against. If Tesseract is not installed, OCR is skipped and we record a
clear warning — the document still works via vision; it just can't be self-grounded
from its own text unless the same systems appear in a text-bearing document.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from ..llm.base import ImageInput
from .loaders import ExtractedDoc

_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".bmp": "image/bmp", ".gif": "image/gif",
    ".tif": "image/tiff", ".tiff": "image/tiff",
}


def _ocr_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 - any failure means OCR is unavailable
        return False


def _ocr_text(path: Path) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(path) as im:
        return pytesseract.image_to_string(im)


def load_image(path: Path) -> ExtractedDoc:
    data = path.read_bytes()
    mime = _MIME.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "image/png"
    image_input = ImageInput(data=data, mime_type=mime)

    warnings: list[str] = []
    text = ""
    method = "vision"
    if _ocr_available():
        try:
            text = _ocr_text(path).strip()
            method = "vision+ocr"
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"OCR failed ({exc}); relying on vision only.")
    else:
        warnings.append(
            "Tesseract OCR not installed — using vision only. Evidence from this image "
            "is grounded only if the same system also appears in a text document. "
            "Install Tesseract for full image self-grounding."
        )

    return ExtractedDoc(
        name=path.name,
        path=str(path),
        media_type="image",
        text=text,
        images=[image_input],
        pages=1,
        ingest_method=method,
        warnings=warnings,
    )
