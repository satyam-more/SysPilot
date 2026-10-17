"""
Tests for the authentication layer.
"""

import hashlib
import secrets

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.api.auth as auth_module
from backend.api.auth import (
    _BROWSER_ORIGINS,
    _SESSION_TOKEN,
    validate_browser_request,
    validate_shell_request,
    init_auth,
    get_session_token,
    _SHELL_TOKEN_PATH,
)


# ---------------------------------------------------------------------------
# Browser Origins
# ---------------------------------------------------------------------------

class TestBrowserOrigins:
    def test_localhost_8000_in_origins(self):
        assert "http://localhost:8000" in _BROWSER_ORIGINS

    def test_vite_dev_origin_in_origins(self):
        assert "http://localhost:5173" in _BROWSER_ORIGINS

    def test_evil_origin_not_in_origins(self):
        assert "http://evil.com" not in _BROWSER_ORIGINS

    def test_null_not_in_origins(self):
        assert "null" not in _BROWSER_ORIGINS


# ---------------------------------------------------------------------------
# Session token
# ---------------------------------------------------------------------------

class TestSessionToken:
    def test_token_is_nonempty_string(self):
        assert isinstance(_SESSION_TOKEN, str)
        assert len(_SESSION_TOKEN) > 0

    def test_get_session_token_returns_same(self):
        assert get_session_token() == _SESSION_TOKEN


# ---------------------------------------------------------------------------
# Shell token
# ---------------------------------------------------------------------------

class TestInitAuth:
    def test_shell_token_written_to_file(self, tmp_path, monkeypatch):
        token_path = tmp_path / "shell_token"
        monkeypatch.setattr(auth_module, "_SHELL_TOKEN_PATH", token_path)
        monkeypatch.setattr(auth_module, "_shell_token", None)
        init_auth()
        assert token_path.exists()
        content = token_path.read_text().strip()
        assert len(content) > 0

    def test_shell_token_file_mode_600(self, tmp_path, monkeypatch):
        token_path = tmp_path / "shell_token"
        monkeypatch.setattr(auth_module, "_SHELL_TOKEN_PATH", token_path)
        monkeypatch.setattr(auth_module, "_shell_token", None)
        init_auth()
        mode = oct(token_path.stat().st_mode)[-3:]
        assert mode == "600"


# ---------------------------------------------------------------------------
# Full-stack route auth tests via TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """TestClient with the full app — triggers lifespan (init_db + init_auth)."""
    from backend.main import app
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def session_token():
    return get_session_token()


@pytest.fixture
def shell_token():
    if auth_module._shell_token is None:
        init_auth()
    return auth_module._shell_token


class TestBrowserRequestValidation:
    def test_valid_origin_and_token_accepted(self, client, session_token):
        resp = client.get(
            "/api/events",
            headers={
                "Origin": "http://localhost:5173",
                "X-Session-Token": session_token,
            },
        )
        assert resp.status_code == 200

    def test_missing_origin_allowed_with_valid_token(self, client, session_token):
        # Desktop WebView makes same-origin requests without an Origin header.
        # This is allowed because the valid session token is still required and
        # a cross-origin browser attack always carries an Origin header.
        resp = client.get(
            "/api/events",
            headers={"X-Session-Token": session_token},
        )
        assert resp.status_code == 200

    def test_missing_origin_rejected_without_token(self, client):
        # Missing Origin AND missing/invalid token must still be rejected.
        resp = client.get("/api/events")
        assert resp.status_code == 403

    def test_null_origin_rejected(self, client, session_token):
        resp = client.get(
            "/api/events",
            headers={"Origin": "null", "X-Session-Token": session_token},
        )
        assert resp.status_code == 403

    def test_disallowed_origin_rejected(self, client, session_token):
        resp = client.get(
            "/api/events",
            headers={"Origin": "http://evil.com", "X-Session-Token": session_token},
        )
        assert resp.status_code == 403

    def test_wrong_token_rejected(self, client):
        resp = client.get(
            "/api/events",
            headers={
                "Origin": "http://localhost:5173",
                "X-Session-Token": "wrongtoken",
            },
        )
        assert resp.status_code == 403

    def test_missing_token_rejected(self, client):
        resp = client.get(
            "/api/events",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 403


class TestShellRequestValidation:
    def test_valid_shell_token_accepted(self, client, shell_token):
        resp = client.post(
            "/api/events",
            json={
                "source": "shell",
                "event_type": "command_run",
                "content_excerpt": "cargo run",
            },
            headers={"X-Shell-Token": shell_token},
        )
        assert resp.status_code == 201

    def test_missing_shell_token_rejected(self, client):
        resp = client.post(
            "/api/events",
            json={
                "source": "shell",
                "event_type": "command_run",
                "content_excerpt": "cargo run",
            },
        )
        assert resp.status_code == 403

    def test_wrong_shell_token_rejected(self, client):
        resp = client.post(
            "/api/events",
            json={
                "source": "shell",
                "event_type": "command_run",
                "content_excerpt": "cargo run",
            },
            headers={"X-Shell-Token": "wrongshelltoken"},
        )
        assert resp.status_code == 403
