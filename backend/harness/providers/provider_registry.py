"""
Provider registry — manages which provider is active.

Persists mode and API config to the provider_config table.
The agent loop calls get_active_provider() to get the current provider.
"""

import logging
from datetime import datetime, timezone
from typing import Literal

from backend.database.db import get_connection
from backend.harness.providers.api_provider import APIProvider
from backend.harness.providers.base import ModelProvider, ProviderStatus
from backend.harness.providers.ollama_provider import OllamaProvider
from backend.security.keystore import KeyStoreResult, delete_key, key_is_configured, mask_key, save_key

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
        "default_model": "gpt-4o-mini",
    },
}

_current_mode: Literal["offline", "api"] = "offline"
_api_config: dict = {"provider": "openai", "model": "gpt-4o-mini", "key_ref": ""}


def _load_config() -> None:
    """
    Load saved mode and config from DB on startup.
    If a key_ref is present and the key is still configured in the keystore,
    default to API mode so the saved OpenAI key is used automatically.
    """
    global _current_mode, _api_config
    conn = get_connection()
    row = conn.execute("SELECT * FROM provider_config WHERE id = 1").fetchone()
    if row:
        provider_name = row["provider_name"] or "openai"
        key_ref = row["key_ref"] or ""
        _api_config = {
            "provider": provider_name,
            "model": "gpt-4o-mini",  # model not persisted separately in first release
            "key_ref": key_ref,
        }
        # Prefer API mode when a usable key exists; otherwise offline.
        if key_ref and key_is_configured(provider_name):
            _current_mode = "api"
        else:
            _current_mode = "offline"
    logger.info("Provider registry loaded: mode=%s", _current_mode)


def get_active_provider() -> ModelProvider:
    """Return the currently active provider instance."""
    if _current_mode == "api":
        return APIProvider(
            provider=_api_config["provider"],
            model=_api_config["model"],
            key_ref=_api_config["key_ref"],
        )
    return OllamaProvider()


def get_status() -> ProviderStatus:
    """Return current provider status without making a network call."""
    from backend.security.keystore import storage_is_persistent

    provider = get_active_provider()
    model = provider.get_active_model()
    # Always report the REAL key state, regardless of mode. Previously this
    # hardcoded True in offline mode, which made the UI falsely claim a key
    # was configured when none existed.
    configured = key_is_configured(_api_config["provider"])
    persistent = storage_is_persistent(_api_config["provider"])
    return ProviderStatus(
        mode=_current_mode,
        model=model,
        connected=False,  # not checked here — use health_check for that
        error=None,
        key_configured=configured,
        key_persistent=persistent,
    )


async def health_check() -> ProviderStatus:
    """Run the active provider's health check."""
    provider = get_active_provider()
    return await provider.health_check()


def set_mode(mode: Literal["offline", "api"]) -> None:
    """Set the active mode. Raises ValueError if switching to api with no key."""
    if mode == "api" and not key_is_configured(_api_config["provider"]):
        raise ValueError("Cannot switch to API mode — no API key configured")
    global _current_mode
    _current_mode = mode
    _persist()


def set_api_config(provider: str, model: str, key: str) -> dict:
    """
    Save API key and update config. Automatically switches to API mode so the
    saved key is used immediately — the user does not need a separate toggle.
    Returns {"status": "saved", "masked_key": "sk-••••••••"}.
    """
    global _api_config, _current_mode
    result = save_key(provider, key)
    _api_config = {
        "provider": provider,
        "model": model,
        "key_ref": result.key_ref,
    }
    # Auto-switch to API mode now that a key is configured.
    _current_mode = "api"
    _persist()
    return {"status": "saved", "masked_key": mask_key(key), "mode": "api"}


def remove_api_key() -> None:
    """Delete the API key and reset to offline mode."""
    global _current_mode, _api_config
    key_ref = _api_config.get("key_ref", "")
    if key_ref:
        delete_key(key_ref)
    _current_mode = "offline"
    _api_config = {"provider": "openai", "model": "gpt-4o-mini", "key_ref": ""}
    _persist()


def get_providers() -> list[dict]:
    """Return list of supported providers and their models."""
    return [
        {"name": key, "models": val["models"]}
        for key, val in SUPPORTED_PROVIDERS.items()
    ]


def _persist() -> None:
    """Save current config to the provider_config table."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    persistent = 1 if _current_mode == "api" else 0
    key_ref = _api_config.get("key_ref") or None
    conn.execute(
        """
        INSERT INTO provider_config (id, provider_name, key_ref, persistent, updated_at)
        VALUES (1, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            provider_name = excluded.provider_name,
            key_ref = excluded.key_ref,
            persistent = excluded.persistent,
            updated_at = excluded.updated_at
        """,
        (_api_config["provider"], key_ref, persistent, now),
    )
