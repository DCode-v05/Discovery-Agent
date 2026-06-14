"""Gemini provider (google-genai).

Handles vision + structured extraction + reasoning. Uses native structured output
via `response_schema` (a Pydantic model) so the model is constrained to our schema.
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from .base import BaseLLMProvider, ImageInput, LLMResult, RateLimiter
from .errors import ProviderUnavailableError


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, rpm: int, max_retries: int = 5):
        super().__init__(RateLimiter(rpm), max_retries)
        try:
            from google import genai  # noqa: PLC0415 - lazy so the app imports without the SDK
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailableError(
                "google-genai is not installed.",
                needs="pip install google-genai", provider=self.name,
            ) from exc
        self._genai = genai
        self._client = genai.Client(api_key=api_key)

    def _build_contents(self, prompt: str, images: list[ImageInput] | None):
        from google.genai import types  # noqa: PLC0415
        contents: list = []
        for img in images or []:
            contents.append(types.Part.from_bytes(data=img.data, mime_type=img.mime_type))
        contents.append(prompt)
        return contents

    def _raw_structured(self, *, schema: type[BaseModel], prompt: str, system: str,
                        model: str, images: list[ImageInput] | None) -> LLMResult:
        from google.genai import types  # noqa: PLC0415
        # NOTE: we do NOT use Gemini's `response_schema`. Pydantic models carry field
        # defaults, and Gemini's structured-output schema rejects `default` (and several
        # other JSON-schema features). Instead we force JSON output and inject the schema
        # into the system instruction; the base class validates/repairs against Pydantic.
        schema_json = json.dumps(schema.model_json_schema())
        sys = (system + "\n\n" if system else "") + (
            "You MUST respond with a single JSON object that conforms to this JSON Schema. "
            "Return ONLY the JSON — no markdown fences, no commentary.\n"
            f"JSON Schema:\n{schema_json}"
        )
        config = types.GenerateContentConfig(
            system_instruction=sys,
            response_mime_type="application/json",
            temperature=0.0,
        )
        resp = self._client.models.generate_content(
            model=model, contents=self._build_contents(prompt, images), config=config,
        )
        return LLMResult(
            text=getattr(resp, "text", "") or "",
            parsed=None,  # base class validates `text` against the Pydantic schema
            provider=self.name, model=model, latency_ms=0.0,
            tokens=self._tokens(resp),
        )

    def _raw_text(self, *, prompt: str, system: str, model: str,
                 images: list[ImageInput] | None) -> LLMResult:
        from google.genai import types  # noqa: PLC0415
        config = types.GenerateContentConfig(
            system_instruction=system or None, temperature=0.1,
        )
        resp = self._client.models.generate_content(
            model=model, contents=self._build_contents(prompt, images), config=config,
        )
        return LLMResult(
            text=getattr(resp, "text", "") or "",
            parsed=None, provider=self.name, model=model, latency_ms=0.0,
            tokens=self._tokens(resp),
        )

    @staticmethod
    def _tokens(resp) -> int | None:
        usage = getattr(resp, "usage_metadata", None)
        return getattr(usage, "total_token_count", None) if usage else None
