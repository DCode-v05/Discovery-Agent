"""Groq provider (OpenAI-compatible Llama models).

Handles fast code generation (Level 3). Structured output uses JSON-object mode
with the target JSON Schema injected into the system prompt; the base class then
validates the response against the Pydantic schema (with automatic retry/repair).
"""
from __future__ import annotations

import base64
import json

from pydantic import BaseModel

from .base import BaseLLMProvider, ImageInput, LLMResult, RateLimiter
from .errors import ProviderUnavailableError


class GroqProvider(BaseLLMProvider):
    name = "groq"

    def __init__(self, api_key: str, rpm: int, max_retries: int = 5):
        super().__init__(RateLimiter(rpm), max_retries)
        try:
            from groq import Groq  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailableError(
                "groq is not installed.", needs="pip install groq", provider=self.name,
            ) from exc
        self._client = Groq(api_key=api_key)

    def _user_content(self, prompt: str, images: list[ImageInput] | None):
        if not images:
            return prompt
        parts: list[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = base64.b64encode(img.data).decode("ascii")
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img.mime_type};base64,{b64}"},
            })
        return parts

    def _raw_structured(self, *, schema: type[BaseModel], prompt: str, system: str,
                        model: str, images: list[ImageInput] | None) -> LLMResult:
        schema_json = json.dumps(schema.model_json_schema())
        sys = (system + "\n\n" if system else "") + (
            "Respond ONLY with a single JSON object that conforms to this JSON Schema. "
            "Do not include markdown fences or any prose outside the JSON.\n"
            f"JSON Schema:\n{schema_json}"
        )
        completion = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": self._user_content(prompt, images)},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        text = completion.choices[0].message.content or ""
        return LLMResult(text=text, parsed=None, provider=self.name, model=model,
                         latency_ms=0.0, tokens=self._tokens(completion))

    def _raw_text(self, *, prompt: str, system: str, model: str,
                 images: list[ImageInput] | None) -> LLMResult:
        completion = self._client.chat.completions.create(
            model=model,
            messages=[
                *([{"role": "system", "content": system}] if system else []),
                {"role": "user", "content": self._user_content(prompt, images)},
            ],
            temperature=0.2,
        )
        text = completion.choices[0].message.content or ""
        return LLMResult(text=text, parsed=None, provider=self.name, model=model,
                         latency_ms=0.0, tokens=self._tokens(completion))

    @staticmethod
    def _tokens(completion) -> int | None:
        usage = getattr(completion, "usage", None)
        return getattr(usage, "total_tokens", None) if usage else None
