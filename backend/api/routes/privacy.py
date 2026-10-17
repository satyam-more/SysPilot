"""
Privacy API routes.

POST /api/privacy/pause   — activate privacy mode
POST /api/privacy/resume  — deactivate privacy mode
GET  /api/privacy/status  — current state + collector acknowledgment

All mutable endpoints require browser auth (Origin + session token).
"""

from fastapi import APIRouter, Depends, Request

from backend.api.auth import validate_browser_request
from backend.privacy.controller import privacy_controller

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


@router.post("/pause")
def pause(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Activate privacy mode. Drops all subsequent ingestion until resumed."""
    result = privacy_controller.activate_privacy()
    return result


@router.post("/resume")
def resume(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Resume normal recording and restart collectors that were stopped."""
    privacy_controller.deactivate_privacy()
    # Restart collectors that were stopped on pause.
    from backend.collectors.filesystem import filesystem_collector
    from backend.collectors.browser_history import browser_collector
    filesystem_collector.start()
    browser_collector.start()
    return {"state": "active"}


@router.get("/status")
def status() -> dict:
    """Return current privacy state and per-collector acknowledgment."""
    return privacy_controller.get_status()
