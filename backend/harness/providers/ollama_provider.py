"""
Offline model provider — Ollama.

Uses the local Ollama API at http://localhost:11434.
No API key required. No outbound network calls beyond localhost.
"""

import logging
from typing import Literal

import httpx

from backend.harness.providers.base import ModelProvider, ProviderStatus

logger = logging.getLogger(__name__)

_OLLAMA_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "qwen2.5:3b"


class OllamaProvider(ModelProvider):
    def __init__(self, model: str = _DEFAULT_MODEL):
        self._model = model

    async def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> dict:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(
            base_url=_OLLAMA_BASE_URL,
            timeout=httpx.Timeout(60.0),
        ) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> ProviderStatus:
        try:
            async with httpx.AsyncClient(
                base_url=_OLLAMA_BASE_URL,
                timeout=httpx.Timeout(10.0),
            ) as client:
                resp = await client.get("/api/tags")
                resp.raise_for_status()
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                connected = self._model in model_names or any(
                    m.startswith(self._model) for m in model_names
                )
                return ProviderStatus(
                    mode="offline",
                    model=self._model,
                    connected=connected,
                    error=None if connected else f"Model {self._model} not found. Run: ollama pull {self._model}",
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return ProviderStatus(
                mode="offline",
                model=self._model,
                connected=False,
                error="Ollama is not running. Start it with: ollama serve",
            )

    def get_active_model(self) -> str:
        return self._model
