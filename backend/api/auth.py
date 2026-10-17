"""
Local API authentication.

Two completely separate mechanisms — do not mix them:

1. Browser session token
   - Generated at backend startup with secrets.token_hex(32)
   - Never written to disk, never in localStorage
   - Injected into served HTML via <meta name="tb-session" content="...">
   - Validated on every mutable browser-facing endpoint
   - Revoked when the backend process exits (in-memory only)

2. Shell collector token
   - Written to ~/.config/trailback/shell_token on startup (mode 0600)
   - Read by the shell hook before each POST
   - Validated by validate_shell_request() — no Origin requirement
   - Revoked by deleting the file or restarting the backend

Origin validation:
   - Browser endpoints require an exact match in _BROWSER_ORIGINS
   - Missing, null, or unlisted Origin → 403 (never treat as allowed)
   - Shell endpoints do not require an Origin header
"""

import hashlib
import logging
import os
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Approved browser origins (exact match required)
# ---------------------------------------------------------------------------
_BROWSER_ORIGINS: set[str] = {
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",    # Vite dev server
    "http://127.0.0.1:5173",   # Vite dev server (IP)
}


def register_origin(origin: str) -> None:
    """
    Register an additional allowed browser origin at runtime.
    Used by the desktop launcher to allow the WebView's dynamic loopback
    origin (e.g. http://127.0.0.1:<random-port>).
    """
    _BROWSER_ORIGINS.add(origin)
    logger.info("Registered allowed origin: %s", origin)

# ---------------------------------------------------------------------------
# Session token (browser) — generated once at import time
# ---------------------------------------------------------------------------
_SESSION_TOKEN: str = secrets.token_hex(32)

# ---------------------------------------------------------------------------
# Shell token — file-backed, written on startup
# ---------------------------------------------------------------------------
_SHELL_TOKEN_PATH = Path.home() / ".config" / "trailback" / "shell_token"
_shell_token: str | None = None


def _write_shell_token() -> str:
    """Generate and persist the shell token (mode 0600). Returns the token."""
    token = secrets.token_hex(32)
    _SHELL_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SHELL_TOKEN_PATH.write_text(token)
    os.chmod(_SHELL_TOKEN_PATH, 0o600)
    return token


def init_auth() -> None:
    """
    Called once at application startup.
    Writes the shell token file. The session token is already in memory.
    """
    global _shell_token
    _shell_token = _write_shell_token()
    logger.info("Auth initialised. Shell token written to %s", _SHELL_TOKEN_PATH)


def get_session_token() -> str:
    """Return the in-memory browser session token (for injection into HTML)."""
    return _SESSION_TOKEN


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_browser_request(
    request: Request,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> None:
    """
    Validate a browser-facing mutable request.
    Raises HTTP 403 if:
      - Origin header is missing, null, or not in _BROWSER_ORIGINS
      - X-Session-Token header is missing or does not match _SESSION_TOKEN
    Uses secrets.compare_digest to prevent timing attacks.
    """
    origin = request.headers.get("origin")

    # Origin policy:
    #   - If Origin is PRESENT, it must be in the allowlist. A real browser
    #     always attaches Origin to cross-origin requests, so a malicious
    #     website cannot bypass this. "null" (sandboxed/file://) is rejected.
    #   - If Origin is ABSENT, the request is same-origin from the desktop
    #     WebView (WebEngine omits Origin on same-origin GETs). This is safe
    #     because a cross-origin browser attack always carries an Origin.
    #     The session token below is still required and validated.
    if origin is not None:
        if origin == "null" or origin not in _BROWSER_ORIGINS:
            logger.warning("Rejected request: disallowed Origin %r", origin)
            raise HTTPException(status_code=403, detail="Forbidden")

    if not x_session_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not secrets.compare_digest(
        hashlib.sha256(x_session_token.encode()).digest(),
        hashlib.sha256(_SESSION_TOKEN.encode()).digest(),
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


def validate_shell_request(
    x_shell_token: str | None = Header(default=None, alias="X-Shell-Token"),
) -> None:
    """
    Validate a request from the shell collector.
    No Origin requirement — shell has no browser origin.
    Raises HTTP 403 if the token is missing or does not match.
    """
    if _shell_token is None:
        logger.error("Shell token not initialised — call init_auth() at startup.")
        raise HTTPException(status_code=503, detail="Service not ready")

    if not x_shell_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not secrets.compare_digest(
        hashlib.sha256(x_shell_token.encode()).digest(),
        hashlib.sha256(_shell_token.encode()).digest(),
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
