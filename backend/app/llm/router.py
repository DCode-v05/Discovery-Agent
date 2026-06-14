"""LLM router — the single entry point services use.

Maps a *task* (extraction / vision / gap_analysis / codegen) to the configured
provider + model, lazily constructs providers (so a missing key only fails the
task that needs it), and threads observability through every call.
"""
from __future__ import annotations

from pydantic import BaseModel

from ..config import Settings, get_settings
from ..observability import RunLedger
from .base import BaseLLMProvider, ImageInput
from .errors import MissingAPIKeyError


class LLMRouter:
    def __init__(self, settings: Settings | None = None, ledger: RunLedger | None = None):
        self.settings = settings or get_settings()
        self.ledger = ledger
        self._providers: dict[str, BaseLLMProvider] = {}

    # -- provider construction --------------------------------------------- #
    def provider(self, name: str) -> BaseLLMProvider:
        if name in self._providers:
            return self._providers[name]
        if not self.settings.has_key(name):
            raise MissingAPIKeyError(name)
        if name == "gemini":
            from .gemini_provider import GeminiProvider
            prov: BaseLLMProvider = GeminiProvider(
                self.settings.gemini_api_key, self.settings.gemini_rpm,
                self.settings.llm_max_retries,
            )
        elif name == "groq":
            from .groq_provider import GroqProvider
            prov = GroqProvider(
                self.settings.groq_api_key, self.settings.groq_rpm,
                self.settings.llm_max_retries,
            )
        else:  # pragma: no cover - guarded by config
            raise MissingAPIKeyError(name)
        self._providers[name] = prov
        return prov

    def _model_for(self, task: str, provider: str) -> str:
        s = self.settings
        if provider == "gemini":
            return s.gemini_vision_model if task == "vision" else s.gemini_model
        return s.groq_fast_model if task == "fast" else s.groq_code_model

    # -- public API used by services --------------------------------------- #
    def structured(self, *, task: str, schema: type[BaseModel], prompt: str,
                   system: str = "", images: list[ImageInput] | None = None,
                   model: str | None = None) -> BaseModel:
        provider_name = self.settings.provider_for(task)
        prov = self.provider(provider_name)
        chosen = model or self._model_for(task, provider_name)
        if self.ledger:
            self.ledger.decision(
                what=f"llm:{task}", choice=f"{provider_name}/{chosen}",
                why="configured route for this task",
            )
        res = prov.complete_structured(schema=schema, prompt=prompt, system=system,
                                       model=chosen, images=images, task=task,
                                       ledger=self.ledger)
        return res.parsed

    def text(self, *, task: str, prompt: str, system: str = "",
             images: list[ImageInput] | None = None, model: str | None = None) -> str:
        provider_name = self.settings.provider_for(task)
        prov = self.provider(provider_name)
        chosen = model or self._model_for(task, provider_name)
        if self.ledger:
            self.ledger.decision(
                what=f"llm:{task}", choice=f"{provider_name}/{chosen}",
                why="configured route for this task",
            )
        res = prov.complete_text(prompt=prompt, system=system, model=chosen,
                                 images=images, task=task, ledger=self.ledger)
        return res.text
