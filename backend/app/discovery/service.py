"""Level 1 orchestration: ingest -> extract -> merge -> ground -> policy -> Inventory.

This is where the agent's decisions and guard rails come together:
  * each document is loaded and extracted (failures are recorded, never dropped);
  * findings are merged across documents;
  * the grounding guard verifies evidence against source text;
  * the confidence policy assigns tiers and flags low-confidence/ungrounded systems
    for human review.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..ingest.loaders import (
    ExtractedDoc,
    UnsupportedDocument,
    discover_documents,
    load_document,
)
from ..llm.errors import LLMError
from ..llm.router import LLMRouter
from ..observability import RunLedger
from ..schemas.inventory import (
    ConfidenceTier,
    Inventory,
    SkippedDocument,
    System,
)
from .extractor import extract_from_doc
from .grounding import is_grounded
from .merger import merge_systems

_HALLUCINATION_CAP = 0.49  # ungrounded-but-text-available systems are capped here


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assign_tier(confidence: float) -> ConfidenceTier:
    s = get_settings()
    if confidence >= s.confidence_explicit:
        return ConfidenceTier.explicit
    if confidence >= s.confidence_inferred:
        return ConfidenceTier.inferred
    return ConfidenceTier.review


def run_discovery(source: str | Path, ledger: RunLedger | None = None,
                  router: LLMRouter | None = None) -> Inventory:
    ledger = ledger or RunLedger(kind="discovery")
    router = router or LLMRouter(ledger=ledger)

    paths = discover_documents(source)
    ledger.event("documents_found", count=len(paths), files=[p.name for p in paths])

    loaded: list[ExtractedDoc] = []
    skipped: list[SkippedDocument] = []
    warnings: list[str] = []

    # --- ingest --------------------------------------------------------------
    for p in paths:
        try:
            doc = load_document(p)
            loaded.append(doc)
            for w in doc.warnings:
                warnings.append(f"{doc.name}: {w}")
            ledger.event("document_loaded", document=doc.name, media_type=doc.media_type,
                         method=doc.ingest_method, chars=len(doc.text), images=len(doc.images))
        except UnsupportedDocument as exc:
            skipped.append(SkippedDocument(document=p.name, reason=str(exc), needs=exc.needs))
            ledger.failure(what=f"load:{p.name}", error=str(exc), needs=exc.needs)
        except Exception as exc:  # noqa: BLE001 - any loader failure is reported, not fatal
            skipped.append(SkippedDocument(document=p.name, reason=str(exc),
                                           needs="Check the file is not corrupt and is a supported format."))
            ledger.failure(what=f"load:{p.name}", error=str(exc),
                           needs="Check the file is not corrupt and is a supported format.")

    # --- extract -------------------------------------------------------------
    per_doc = []
    for doc in loaded:
        try:
            systems = extract_from_doc(doc, router, ledger)
            per_doc.append((doc, systems))
        except LLMError as exc:
            skipped.append(SkippedDocument(document=doc.name, reason=exc.message, needs=exc.needs))
            ledger.failure(what=f"extract:{doc.name}", error=exc.message, needs=exc.needs)
        except Exception as exc:  # noqa: BLE001
            skipped.append(SkippedDocument(document=doc.name, reason=str(exc),
                                           needs="Unexpected extraction error; see logs."))
            ledger.failure(what=f"extract:{doc.name}", error=str(exc),
                           needs="Unexpected extraction error; see logs.")

    # --- merge ---------------------------------------------------------------
    systems = merge_systems(per_doc)
    ledger.event("merged", systems=len(systems))

    # --- ground + policy -----------------------------------------------------
    text_map = {doc.name: doc.text for doc in loaded}
    docs_with_text = {doc.name for doc in loaded if doc.has_text}
    for sys in systems:
        _apply_grounding_and_policy(sys, text_map, docs_with_text, ledger)

    inv = Inventory(
        run_id=ledger.run_id,
        generated_at=_now(),
        document_count=len(loaded),
        systems_count=len(systems),
        systems=systems,
        warnings=warnings,
        skipped_documents=skipped,
    )
    ledger.finish(
        documents=len(loaded), skipped=len(skipped), systems=len(systems),
        flagged_for_review=sum(1 for s in systems if s.needs_review),
    )
    return inv


def _apply_grounding_and_policy(sys: System, text_map: dict[str, str],
                                docs_with_text: set[str], ledger: RunLedger) -> None:
    grounded_any = False
    for e in sys.evidence:
        e.grounded = is_grounded(e.quote, text_map.get(e.source_doc, ""))
        grounded_any = grounded_any or e.grounded

    has_text_source = any(e.source_doc in docs_with_text for e in sys.evidence)

    if not grounded_any and has_text_source:
        # Claims a quote that isn't in the source text — the signature of a hallucination.
        sys.confidence = min(sys.confidence, _HALLUCINATION_CAP)
        _append_note(sys, "Evidence could not be verified against the source document "
                          "text (possible hallucination); flagged for review.")
        ledger.event("grounding_failed", level="warning", system=sys.name,
                     why="evidence not found in source text")
    elif not grounded_any and not has_text_source:
        _append_note(sys, "Vision/image-sourced with no text layer to self-verify; "
                          "corroborate or install OCR for grounding.")
        ledger.event("grounding_unverifiable", level="warning", system=sys.name,
                     why="image-only source, OCR unavailable")

    sys.confidence_tier = _assign_tier(sys.confidence)
    sys.needs_review = sys.confidence_tier == ConfidenceTier.review or (
        not grounded_any and has_text_source)
    ledger.confidence(subject=sys.name, score=round(sys.confidence, 3),
                      tier=sys.confidence_tier.value, note=sys.uncertainty_note)


def _append_note(sys: System, note: str) -> None:
    sys.uncertainty_note = (sys.uncertainty_note + "; " + note) if sys.uncertainty_note else note


# --------------------------------------------------------------------------- #
# Human-readable report                                                       #
# --------------------------------------------------------------------------- #
def to_markdown(inv: Inventory) -> str:
    lines = [
        "# System Discovery Report",
        "",
        f"- **Run:** `{inv.run_id}`",
        f"- **Generated:** {inv.generated_at}",
        f"- **Documents processed:** {inv.document_count}",
        f"- **Systems discovered:** {inv.systems_count}",
        f"- **Flagged for review:** {sum(1 for s in inv.systems if s.needs_review)}",
        "",
    ]
    if inv.skipped_documents:
        lines += ["## ⚠️ Skipped documents", ""]
        for sk in inv.skipped_documents:
            lines.append(f"- **{sk.document}** — {sk.reason} _(needs: {sk.needs})_")
        lines.append("")

    lines += ["## Discovered systems", ""]
    for s in inv.systems:
        flag = " 🔎 _review_" if s.needs_review else ""
        lines.append(f"### {s.name} — {s.category}{flag}")
        lines.append(
            f"- **Confidence:** {s.confidence:.0%} ({s.confidence_tier.value}) "
            f"| **Criticality:** {s.criticality.value} | **Auth:** {s.auth_method}")
        if s.key_entities:
            lines.append(f"- **Key entities:** {', '.join(s.key_entities)}")
        if s.business_processes:
            lines.append(f"- **Processes:** {', '.join(s.business_processes)}")
        if s.uncertainty_note:
            lines.append(f"- **Uncertainty:** {s.uncertainty_note}")
        lines.append(f"- **Sources:** {', '.join(s.source_docs)}")
        for e in s.evidence:
            mark = "✓" if e.grounded else "✗"
            lines.append(f"    - {mark} _\"{e.quote.strip()[:160]}\"_ — {e.source_doc} ({e.location})")
        lines.append("")
    if inv.warnings:
        lines += ["## Notes", ""] + [f"- {w}" for w in inv.warnings]
    return "\n".join(lines)
