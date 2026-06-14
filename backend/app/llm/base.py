"""Provider-agnostic base: shared types, rate limiting, JSON helpers, and the
abstract provider interface.

Concrete providers (Gemini, Groq) subclass `BaseLLMProvider` and implement the
two `_raw_*` methods; the public `complete_*` methods add rate limiting, retries,
validation, and observability for free.
"""
from __future__ import annotations

import json
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import LLMResponseError

if TYPE_CHECKING:
    from ..observability import RunLedger

T = TypeVar("T", bound=BaseModel)


@dataclass
class ImageInput:
    data: bytes
    mime_type: str = "image/png"


@dataclass
class LLMResult:
    text: str
    parsed: Any | None
    provider: str
    model: str
    latency_ms: float
    tokens: int | None = None


class RateLimiter:
    """Minimal thread-safe spacing limiter: enforces >= 60/rpm seconds between calls.

    Free tiers are RPM-bounded; spacing calls is simpler and safer than a burst
    bucket for this workload, and keeps us well under the limit.
    """

    def __init__(self, rpm: int):
        self.min_interval = 60.0 / max(rpm, 1)
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self.min_interval - (now - self._last)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()


def strip_code_fences(text: str) -> str:
    """Remove a leading/trailing ```lang fence if the model wrapped its output."""
    t = text.strip()
    if t.startswith("```"):
        # drop first fence line
        t = re.sub(r"^```[a-zA-Z0-9_+-]*\n", "", t)
        if t.rstrip().endswith("```"):
            t = t.rstrip()[: -3]
    return t.strip()


def extract_json(text: str) -> str:
    """Best-effort: pull the first JSON object/array out of a model response."""
    t = strip_code_fences(text)
    # Fast path: already valid
    try:
        json.loads(t)
        return t
    except json.JSONDecodeError:
        pass
    # Find the outermost {...} or [...]
    start = min((i for i in (t.find("{"), t.find("[")) if i != -1), default=-1)
    if start == -1:
        return t
    opener = t[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    for i in range(start, len(t)):
        if t[i] == opener:
            depth += 1
        elif t[i] == closer:
            depth -= 1
            if depth == 0:
                return t[start : i + 1]
    return t[start:]


class BaseLLMProvider(ABC):
    """Common behaviour for every provider."""

    name: str = "base"

    def __init__(self, rate_limiter: RateLimiter, max_retries: int = 5):
        self.rate_limiter = rate_limiter
        self.max_retries = max_retries

    # -- subclass hooks ----------------------------------------------------- #
    @abstractmethod
    def _raw_structured(
        self, *, schema: type[BaseModel], prompt: str, system: str, model: str,
        images: list[ImageInput] | None,
    ) -> LLMResult:
        """Return an LLMResult whose `.parsed` is an instance of `schema` (or whose
        `.text` is JSON validatable against it)."""

    @abstractmethod
    def _raw_text(
        self, *, prompt: str, system: str, model: str, images: list[ImageInput] | None,
    ) -> LLMResult:
        ...

    # -- public API --------------------------------------------------------- #
    def complete_structured(
        self, *, schema: type[T], prompt: str, model: str, system: str = "",
        images: list[ImageInput] | None = None, task: str = "",
        ledger: "RunLedger | None" = None,
    ) -> LLMResult:
        def _call() -> LLMResult:
            self.rate_limiter.wait()
            t0 = time.monotonic()
            res = self._raw_structured(schema=schema, prompt=prompt, system=system,
                                       model=model, images=images)
            res.latency_ms = (time.monotonic() - t0) * 1000
            # Ensure .parsed is a validated instance of the schema.
            if not isinstance(res.parsed, schema):
                payload = extract_json(res.text)
                try:
                    res.parsed = schema.model_validate_json(payload)
                except (ValidationError, ValueError) as exc:
                    raise LLMResponseError(
                        f"{self.name} returned output that did not match {schema.__name__}.",
                        needs="Usually transient — retried automatically; if persistent, try a different model in .env.",
                        provider=self.name, model=model,
                    ) from exc
            return res

        res = self._with_retries(_call, model=model)
        if ledger is not None:
            ledger.llm_call(self.name, model, task or "structured", res.latency_ms, res.tokens)
        return res

    def complete_text(
        self, *, prompt: str, model: str, system: str = "",
        images: list[ImageInput] | None = None, task: str = "",
        ledger: "RunLedger | None" = None,
    ) -> LLMResult:
        def _call() -> LLMResult:
            self.rate_limiter.wait()
            t0 = time.monotonic()
            res = self._raw_text(prompt=prompt, system=system, model=model, images=images)
            res.latency_ms = (time.monotonic() - t0) * 1000
            return res

        res = self._with_retries(_call, model=model)
        if ledger is not None:
            ledger.llm_call(self.name, model, task or "text", res.latency_ms, res.tokens)
        return res

    # -- retry wrapper ------------------------------------------------------ #
    def _with_retries(self, fn, *, model: str) -> LLMResult:
        from .errors import LLMError, LLMRateLimitError, ProviderUnavailableError

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return fn()
            except LLMError:
                raise  # already typed and clear — don't wrap
            except Exception as exc:  # noqa: BLE001 - normalise SDK errors below
                last_exc = exc
                msg = str(exc).lower()
                transient = any(k in msg for k in (
                    "rate", "429", "quota", "timeout", "temporar", "overload",
                    "503", "500", "unavailable", "deadline",
                ))
                if not transient or attempt == self.max_retries - 1:
                    break
                # Exponential backoff: 1s, 2s, 4s, ... (free-tier friendly)
                time.sleep(min(2 ** attempt, 30))
        # Out of retries / non-transient
        text = str(last_exc) if last_exc else "unknown error"
        if any(k in text.lower() for k in ("rate", "429", "quota")):
            raise LLMRateLimitError(
                f"{self.name} rate limit / quota exhausted: {text}",
                needs="Wait for the free-tier window to reset, lower the RPM in .env, or switch providers.",
                provider=self.name, model=model,
            )
        raise ProviderUnavailableError(
            f"{self.name} call failed: {text}",
            needs="Check the API key, network access, and that the model id in .env is valid.",
            provider=self.name, model=model,
        )
