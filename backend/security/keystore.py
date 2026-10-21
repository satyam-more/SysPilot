"""
Secure API key storage — two-tier keystore.

Tier 1: OS secret store (keyring/libsecret on Ubuntu) — persistent.
Tier 2: Session-only in-memory dict — lost on restart, warned in UI.
No tier 3: never write to plaintext file. Fail closed on unexpected errors.
"""

import keyring
import keyring.errors
import logging

_SERVICE_NAME = "syspilot"
_session_store: dict[str, str] = {}  # in-memory fallback only

logger = logging.getLogger(__name__)


class KeyNotFoundError(Exception):
    pass


class KeyStorageUnavailableError(Exception):
    pass


# All keyring exceptions that indicate the backend is unavailable or locked.
# Treating these as expected fallback conditions.
_KEYRING_UNAVAILABLE = (
    keyring.errors.NoKeyringError,       # no keyring backend installed
    keyring.errors.KeyringLocked,        # keyring exists but is locked
)

# keyring.errors.KeyringError is the base class for all keyring exceptions.
# Any exception that is NOT in _KEYRING_UNAVAILABLE is unexpected
# (e.g. a backend bug, permission error, corrupted store). Fail closed.


class KeyStoreResult:
    def __init__(self, key_ref: str, persistent: bool):
        self.key_ref = key_ref          # opaque reference, never the key itself
        self.persistent = persistent    # False when using session-only store


def save_key(provider: str, key: str) -> KeyStoreResult:
    """
    Store key. Returns opaque key_ref. The key value is never returned.
    Tier 1: OS secret store (persistent).
    Tier 2: session-only in-memory dict (lost on restart, warned in UI).
    No tier 3: never write to plaintext file. Raise on unexpected errors.
    """
    key_ref = f"{provider}_key"
    try:
        keyring.set_password(_SERVICE_NAME, key_ref, key)
        return KeyStoreResult(key_ref=key_ref, persistent=True)
    except _KEYRING_UNAVAILABLE:
        # Expected: backend absent or locked. Fall back to session store.
        logger.warning(
            "OS secret store unavailable for provider %r — key stored in "
            "memory only and will not persist across restarts.",
            provider,
        )
        _session_store[key_ref] = key
        return KeyStoreResult(key_ref=key_ref, persistent=False)
    except keyring.errors.KeyringError as exc:
        # Unexpected keyring error (e.g. corrupted store, permission denied).
        # Fail closed — do not write to plaintext, do not silently swallow.
        logger.error(
            "Unexpected keyring error saving key for provider %r: %s. "
            "API mode is unavailable until this is resolved.",
            provider,
            type(exc).__name__,
        )
        raise KeyStorageUnavailableError(
            f"API key storage failed unexpectedly ({type(exc).__name__}). "
            "Check system keyring configuration."
        ) from exc


def get_key(key_ref: str) -> str:
    """
    Retrieve key at request time. Called by backend only, never by frontend.
    Checks OS store first, then session fallback.
    Fails closed on unexpected keyring errors — does not fall back to plaintext.
    """
    try:
        key = keyring.get_password(_SERVICE_NAME, key_ref)
        if key is not None:
            return key
        # OS store responded but had no entry — fall through to session store.
    except _KEYRING_UNAVAILABLE:
        pass  # Expected unavailability — check session store below.
    except keyring.errors.KeyringError as exc:
        logger.error(
            "Unexpected keyring error retrieving key %r: %s",
            key_ref,
            type(exc).__name__,
        )
        raise KeyStorageUnavailableError(
            f"Could not retrieve API key ({type(exc).__name__})."
        ) from exc

    key = _session_store.get(key_ref)
    if key is not None:
        return key
    raise KeyNotFoundError(f"Key not found: {key_ref}")


def delete_key(key_ref: str) -> None:
    """Remove key from both tiers. Best-effort — does not raise if already absent."""
    _session_store.pop(key_ref, None)
    try:
        keyring.delete_password(_SERVICE_NAME, key_ref)
    except (keyring.errors.PasswordDeleteError,) + _KEYRING_UNAVAILABLE:
        pass  # Already absent or store unavailable — acceptable.
    except keyring.errors.KeyringError as exc:
        logger.warning(
            "Unexpected keyring error deleting key %r: %s",
            key_ref,
            type(exc).__name__,
        )


def key_is_configured(provider: str) -> bool:
    key_ref = f"{provider}_key"
    if key_ref in _session_store:
        return True
    try:
        return keyring.get_password(_SERVICE_NAME, key_ref) is not None
    except _KEYRING_UNAVAILABLE:
        return False
    except keyring.errors.KeyringError:
        return False  # Unexpected error — report as not configured; fail closed.


def storage_is_persistent(provider: str) -> bool:
    """Returns False when the key is in the session-only store."""
    return f"{provider}_key" not in _session_store


def mask_key(key: str) -> str:
    """Return a masked display string like 'sk-••••[last4]'."""
    if len(key) <= 8:
        return "••••"
    return f"{key[:3]}{'•' * 8}{key[-4:]}"
