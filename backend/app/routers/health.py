"""Health & capability endpoint — also reports which providers are configured."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "providers": {"gemini": s.has_key("gemini"), "groq": s.has_key("groq")},
        "models": {
            "gemini": s.gemini_model,
            "gemini_vision": s.gemini_vision_model,
            "groq_code": s.groq_code_model,
        },
        "routes": {
            "extraction": s.provider_for("extraction"),
            "vision": s.provider_for("vision"),
            "gap_analysis": s.provider_for("gap_analysis"),
            "codegen": s.provider_for("codegen"),
        },
    }
