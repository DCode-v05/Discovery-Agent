"""Cross-document merge & dedup.

The same system often appears in several documents. We merge mentions by a
normalized name key, union their entities/processes, keep the strongest evidence,
and collect one `Evidence` record per mention (with source doc + location).
Confidence-tier assignment and grounding happen later in the service, once all
evidence is collected.
"""
from __future__ import annotations

import re
from collections import Counter

from ..ingest.loaders import ExtractedDoc
from ..schemas.inventory import Criticality, Evidence, ExtractedSystem, System

_CRIT_ORDER = {
    Criticality.critical: 4, Criticality.high: 3, Criticality.medium: 2,
    Criticality.low: 1, Criticality.unknown: 0,
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower()).strip()


def _most_common(values: list[str], skip: set[str]) -> str | None:
    counts = Counter(v for v in values if v and v.strip().lower() not in skip)
    return counts.most_common(1)[0][0] if counts else None


def _union(seq_of_lists: list[list[str]]) -> list[str]:
    seen: dict[str, None] = {}
    for lst in seq_of_lists:
        for item in lst:
            k = item.strip()
            if k and k.lower() not in {x.lower() for x in seen}:
                seen[k] = None
    return list(seen.keys())


def merge_systems(per_doc: list[tuple[ExtractedDoc, list[ExtractedSystem]]]) -> list[System]:
    groups: dict[str, list[tuple[str, ExtractedSystem]]] = {}
    for doc, systems in per_doc:
        for s in systems:
            groups.setdefault(_key(s.name), []).append((doc.name, s))

    merged: list[System] = []
    for _key_name, mentions in groups.items():
        names = [m[1].name for m in mentions]
        # Representative = highest-confidence mention.
        rep_doc, rep = max(mentions, key=lambda m: m[1].confidence)

        category = _most_common([m[1].category for m in mentions], {"", "unknown"}) or rep.category
        auth = _most_common([m[1].auth_method for m in mentions], {"", "unknown"}) or rep.auth_method
        criticality = max((m[1].criticality for m in mentions), key=lambda c: _CRIT_ORDER[c])
        confidence = max(m[1].confidence for m in mentions)

        evidence = [
            Evidence(quote=m[1].evidence_quote, source_doc=m[0], location=m[1].location)
            for m in mentions if m[1].evidence_quote
        ]
        notes = [m[1].uncertainty_note for m in mentions if m[1].uncertainty_note.strip()]
        merged.append(System(
            name=Counter(names).most_common(1)[0][0],
            category=category,
            auth_method=auth,
            key_entities=_union([m[1].key_entities for m in mentions]),
            business_processes=_union([m[1].business_processes for m in mentions]),
            criticality=criticality,
            confidence=confidence,
            confidence_tier="explicit",  # provisional; set in service after grounding
            uncertainty_note="; ".join(dict.fromkeys(notes)) or None,
            evidence=evidence,
            source_docs=list(dict.fromkeys(m[0] for m in mentions)),
        ))
    # Stable, useful ordering: confidence desc then name.
    merged.sort(key=lambda s: (-s.confidence, s.name.lower()))
    return merged
