"""
Model settings API routes.

GET  /api/model/status          — current mode, model, key status
POST /api/model/mode             — switch between offline and api mode
POST /api/model/api-key          — save an API key (returns masked key)
DELETE /api/model/api-key        — remove the key and reset to offline
POST /api/model/test-connection  — health check the active provider
GET  /api/model/providers        — list supported providers and models

All mutable endpoints require browser auth (Origin + session token).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.auth import validate_browser_request
from backend.harness.providers import provider_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/model", tags=["model"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SetModeRequest(BaseModel):
    mode: str = Field(pattern="^(offline|api)$")


class SaveKeyRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    key: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status")
def get_status(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Return current model provider status. Never includes the API key value."""
    status = provider_registry.get_status()
    return {
        "mode": status.mode,
        "model": status.model,
        "connected": status.connected,
        "error": status.error,
        "key_configured": status.key_configured,
        "key_persistent": status.key_persistent,
    }


@router.post("/mode")
def set_mode(
    body: SetModeRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Switch between offline and API mode."""
    try:
        provider_registry.set_mode(body.mode)  # type: ignore
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "mode": body.mode}


@router.post("/api-key")
def save_api_key(
    body: SaveKeyRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Save an API key. Returns masked key — never the full key."""
    try:
        result = provider_registry.set_api_config(body.provider, body.model, body.key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


@router.delete("/api-key", status_code=204)
def delete_api_key(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> None:
    """Remove the API key and reset to offline mode."""
    provider_registry.remove_api_key()


@router.post("/test-connection")
async def test_connection(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Run a health check against the active provider."""
    status = await provider_registry.health_check()
    return {
        "success": status.connected,
        "model": status.model,
        "error": status.error,
    }


@router.get("/providers")
def get_providers(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> list[dict]:
    """Return list of supported providers and their available models."""
    return provider_registry.get_providers()
