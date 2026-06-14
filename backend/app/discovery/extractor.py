"""Per-document system extraction.

Decides the extraction path per document (vision for images, text otherwise),
prompts the model with strict anti-hallucination guard rails, and returns the
model's structured `ExtractedSystem` list. The model is told to copy evidence
verbatim and to calibrate confidence — grounding then verifies it.
"""
from __future__ import annotations

from ..ingest.loaders import ExtractedDoc
from ..llm.router import LLMRouter
from ..observability import RunLedger
from ..schemas.inventory import DocumentExtraction, ExtractedSystem

DISCOVERY_SYSTEM = """You are a meticulous enterprise systems-discovery analyst.
Your ONLY job is to identify software systems/applications that are explicitly
present or strongly implied IN THE DOCUMENT YOU ARE GIVEN.

HARD RULES (these are graded):
- NEVER invent a system. If a system is not supported by the document, do not list it.
- NEVER guess a specific product name from a generic description. If the document
  says "a marketing automation platform" without naming it, record the system name
  as exactly that generic phrase with LOW confidence and an uncertainty note — do
  NOT substitute a real product name (e.g. do not write "Marketo").
- Copy `evidence_quote` VERBATIM from the document. It must be findable in the text.

CONFIDENCE CALIBRATION (0..1):
- 0.95-1.0: the system is named explicitly and described (entities, auth, or process).
- 0.70-0.94: the system is named but with thin context, OR clearly implied.
- below 0.70: mentioned only once in passing, ambiguous, or generic/unnamed. Set an
  uncertainty_note explaining what was inferred and what evidence is missing.

For each system capture: name, category, auth_method (or 'Unknown'), key_entities,
business_processes, criticality, confidence, evidence_quote, location, uncertainty_note."""


def _build_prompt(doc: ExtractedDoc, vision: bool) -> str:
    if vision:
        head = (
            f"The attached image is a document named '{doc.name}'. "
            "Read everything visible in the image and extract the systems."
        )
        if doc.has_text:
            head += f"\n\nAn OCR text layer is also provided for reference:\n---\n{doc.text}\n---"
        head += (
            "\n\nFor `location`, describe where in the image the evidence appears "
            "(e.g. 'row 3', 'header'). Copy evidence text verbatim from what you see."
        )
        return head
    return (
        f"Document name: {doc.name}\nDocument type: {doc.media_type}\n"
        "Extract every software system supported by the text below. Use the page/sheet/"
        "row markers for `location`.\n\n--- DOCUMENT START ---\n"
        f"{doc.text}\n--- DOCUMENT END ---"
    )


def extract_from_doc(doc: ExtractedDoc, router: LLMRouter,
                     ledger: RunLedger | None = None) -> list[ExtractedSystem]:
    """Extract systems from one document. Returns [] for an empty document."""
    use_vision = doc.has_images and bool(doc.images)
    if not use_vision and not doc.has_text:
        if ledger:
            ledger.event("extract_skipped", level="warning", document=doc.name,
                         reason="no text and no image to read")
        return []

    task = "vision" if use_vision else "extraction"
    if ledger:
        ledger.decision(
            what="extraction_path", choice=task, why=(
                "document has an image to read" if use_vision
                else "document has a text layer"),
            document=doc.name, ingest_method=doc.ingest_method,
        )

    result = router.structured(
        task=task,
        schema=DocumentExtraction,
        prompt=_build_prompt(doc, use_vision),
        system=DISCOVERY_SYSTEM,
        images=doc.images if use_vision else None,
    )
    systems = list(result.systems) if isinstance(result, DocumentExtraction) else []
    if ledger:
        ledger.event("extracted", document=doc.name, systems=len(systems),
                     names=[s.name for s in systems])
    return systems
