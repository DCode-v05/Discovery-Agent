"""LLM provider abstraction: swappable Gemini + Groq behind one router."""
from .base import ImageInput, LLMResult
from .errors import (
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    MissingAPIKeyError,
    ProviderUnavailableError,
)
from .router import LLMRouter

__all__ = [
    "ImageInput",
    "LLMResult",
    "LLMRouter",
    "LLMError",
    "MissingAPIKeyError",
    "LLMRateLimitError",
    "LLMResponseError",
    "ProviderUnavailableError",
]
