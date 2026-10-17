"""
Model provider abstract interface.

All providers (offline Ollama, external API) implement this interface.
The agent loop calls generate() — it doesn't care which provider is active.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass
class ProviderStatus:
    mode: Literal["offline", "api"]
    model: str
    connected: bool
    error: str | None = None
    key_configured: bool = False
    key_persistent: bool = False


class ModelProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> dict:
        """Send a chat request and return the parsed response."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        """Check if the provider is reachable and return status."""
        ...

    @abstractmethod
    def get_active_model(self) -> str:
        """Return the name of the model this provider is configured to use."""
        ...
