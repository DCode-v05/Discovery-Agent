"""Grounding — the hallucination guard.

Every claim the agent makes about a system must trace to evidence text that
actually appears in a source document. This module verifies an evidence `quote`
against the source `text`. Models paraphrase, so we accept an exact normalized
substring OR a high token-overlap match — but reject quotes that are largely
absent from the source (the signature of a fabricated finding).
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9]+")


def _normalize(s: str) -> str:
    return _WS.sub(" ", s.lower()).strip()


def _tokens(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


def is_grounded(quote: str, source_text: str, *, min_overlap: float = 0.6) -> bool:
    """Return True if `quote` is supported by `source_text`."""
    if not quote or not source_text:
        return False
    nq, ns = _normalize(quote), _normalize(source_text)
    if not nq:
        return False
    # Exact (normalized) containment — the strong case.
    if nq in ns:
        return True
    # Token-overlap fallback for light paraphrasing.
    q_tokens = [t for t in _tokens(quote) if len(t) > 2]
    if not q_tokens:
        return False
    src_tokens = set(_tokens(source_text))
    present = sum(1 for t in q_tokens if t in src_tokens)
    return (present / len(q_tokens)) >= min_overlap
