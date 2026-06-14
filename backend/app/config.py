"""Central configuration — the single source of truth for keys, model IDs,
routing, thresholds, and rate limits.

Free-tier model names rotate; keep them here (and in `.env`) rather than scattered
through business logic. Loaded once via `get_settings()` (cached).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (backend/app/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-driven settings. Reads `.env` at the project root."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- API keys ---
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # --- Models ---
    gemini_model: str = "gemini-2.5-flash"
    gemini_vision_model: str = "gemini-2.5-flash"
    groq_code_model: str = "llama-3.3-70b-versatile"
    groq_fast_model: str = "llama-3.1-8b-instant"

    # --- Task routing (provider name: "gemini" | "groq") ---
    route_extraction: str = "gemini"
    route_vision: str = "gemini"
    route_gap_analysis: str = "gemini"
    route_codegen: str = "groq"

    # --- Confidence policy (Level 1) ---
    confidence_explicit: float = 0.95
    confidence_inferred: float = 0.70

    # --- Rate limiting ---
    gemini_rpm: int = 10
    groq_rpm: int = 30
    llm_max_retries: int = 5

    # --- Behaviour ---
    strict_ingest: bool = True
    run_ledger_dir: str = "data/runs"

    # --- Derived helpers ---
    @property
    def run_ledger_path(self) -> Path:
        p = PROJECT_ROOT / self.run_ledger_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    def provider_for(self, task: str) -> str:
        """Map a task name to its configured provider."""
        return {
            "extraction": self.route_extraction,
            "vision": self.route_vision,
            "gap_analysis": self.route_gap_analysis,
            "codegen": self.route_codegen,
        }.get(task, "gemini")

    def has_key(self, provider: str) -> bool:
        return bool(self.gemini_api_key) if provider == "gemini" else bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
