"""Typed LLM errors.

These let the agent "know what it cannot access" and "fail clearly" — every
error carries a human-actionable `needs` describing what the operator must do.
"""
from __future__ import annotations


class LLMError(Exception):
    """Base class for all provider errors."""

    def __init__(self, message: str, *, needs: str = "", provider: str = "", model: str = ""):
        super().__init__(message)
        self.message = message
        self.needs = needs
        self.provider = provider
        self.model = model

    def as_dict(self) -> dict[str, str]:
        return {
            "error": self.message,
            "needs": self.needs,
            "provider": self.provider,
            "model": self.model,
        }


class MissingAPIKeyError(LLMError):
    def __init__(self, provider: str):
        env = "GEMINI_API_KEY" if provider == "gemini" else "GROQ_API_KEY"
        super().__init__(
            f"No API key configured for provider '{provider}'.",
            needs=f"Set {env} in your .env file (free key: "
                  + ("https://aistudio.google.com/apikey" if provider == "gemini"
                     else "https://console.groq.com/keys") + ").",
            provider=provider,
        )


class LLMRateLimitError(LLMError):
    """Raised after retries are exhausted on a rate-limited provider."""


class LLMResponseError(LLMError):
    """The provider returned something we could not parse/validate against the schema."""


class ProviderUnavailableError(LLMError):
    """The provider SDK/endpoint could not be reached."""
