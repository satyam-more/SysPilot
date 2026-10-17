"""
Tests for the secure keystore.
"""

import pytest
from unittest.mock import patch, MagicMock

import keyring.errors

import backend.security.keystore as ks_module
from backend.security.keystore import (
    KeyNotFoundError,
    KeyStorageUnavailableError,
    KeyStoreResult,
    delete_key,
    get_key,
    key_is_configured,
    mask_key,
    save_key,
    storage_is_persistent,
)


@pytest.fixture(autouse=True)
def clear_session_store():
    """Reset the in-memory session store before each test."""
    ks_module._session_store.clear()
    yield
    ks_module._session_store.clear()


class TestSaveKey:
    def test_os_store_available_returns_persistent(self):
        with patch("keyring.set_password") as mock_set:
            mock_set.return_value = None
            result = save_key("openai", "sk-testkey123")
        assert result.persistent is True
        assert result.key_ref == "openai_key"

    def test_no_keyring_error_falls_back_to_session(self):
        with patch("keyring.set_password", side_effect=keyring.errors.NoKeyringError()):
            result = save_key("openai", "sk-testkey123")
        assert result.persistent is False
        assert ks_module._session_store.get("openai_key") == "sk-testkey123"

    def test_keyring_locked_falls_back_to_session(self):
        with patch("keyring.set_password", side_effect=keyring.errors.KeyringLocked()):
            result = save_key("openai", "sk-testkey123")
        assert result.persistent is False
        assert "openai_key" in ks_module._session_store

    def test_unexpected_keyring_error_raises_and_no_session_fallback(self):
        with patch("keyring.set_password", side_effect=keyring.errors.KeyringError("boom")):
            with pytest.raises(KeyStorageUnavailableError):
                save_key("openai", "sk-testkey123")
        assert "openai_key" not in ks_module._session_store


class TestGetKey:
    def test_retrieves_from_os_store(self):
        with patch("keyring.get_password", return_value="sk-fromkeyring"):
            result = get_key("openai_key")
        assert result == "sk-fromkeyring"

    def test_falls_back_to_session_store_when_os_unavailable(self):
        ks_module._session_store["openai_key"] = "sk-insession"
        with patch("keyring.get_password", side_effect=keyring.errors.NoKeyringError()):
            result = get_key("openai_key")
        assert result == "sk-insession"

    def test_raises_key_not_found_when_absent_from_both(self):
        with patch("keyring.get_password", return_value=None):
            with pytest.raises(KeyNotFoundError):
                get_key("openai_key")

    def test_unexpected_keyring_error_raises_not_falls_back(self):
        ks_module._session_store["openai_key"] = "sk-insession"
        with patch("keyring.get_password", side_effect=keyring.errors.KeyringError("boom")):
            with pytest.raises(KeyStorageUnavailableError):
                get_key("openai_key")

    def test_os_store_returns_none_then_checks_session(self):
        ks_module._session_store["openai_key"] = "sk-session"
        with patch("keyring.get_password", return_value=None):
            result = get_key("openai_key")
        assert result == "sk-session"


class TestDeleteKey:
    def test_clears_session_store(self):
        ks_module._session_store["openai_key"] = "sk-val"
        with patch("keyring.delete_password"):
            delete_key("openai_key")
        assert "openai_key" not in ks_module._session_store

    def test_does_not_raise_if_already_absent(self):
        with patch("keyring.delete_password", side_effect=keyring.errors.PasswordDeleteError()):
            delete_key("openai_key")  # should not raise


class TestKeyIsConfigured:
    def test_true_when_in_session_store(self):
        ks_module._session_store["openai_key"] = "sk-val"
        assert key_is_configured("openai") is True

    def test_true_when_in_os_store(self):
        with patch("keyring.get_password", return_value="sk-val"):
            assert key_is_configured("openai") is True

    def test_false_when_absent(self):
        with patch("keyring.get_password", return_value=None):
            assert key_is_configured("openai") is False

    def test_false_on_unexpected_error(self):
        with patch("keyring.get_password", side_effect=keyring.errors.KeyringError("boom")):
            assert key_is_configured("openai") is False


class TestStorageIsPersistent:
    def test_true_when_not_in_session_store(self):
        assert storage_is_persistent("openai") is True

    def test_false_when_in_session_store(self):
        ks_module._session_store["openai_key"] = "sk-val"
        assert storage_is_persistent("openai") is False


class TestMaskKey:
    def test_masks_long_key(self):
        masked = mask_key("sk-abcdefghijklmnop1234")
        assert "1234" in masked
        assert "sk-" in masked
        assert "abcdefghijklmnop" not in masked

    def test_masks_short_key(self):
        assert mask_key("short") == "••••"
