"""
Browser-tracking API routes.

Detect installed browsers, enable/disable tracking per browser, manage
excluded domains, and view collector status.

All mutable endpoints require browser auth (Origin + session token).
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.api.auth import validate_browser_request
from backend.collectors import tracking_config
from backend.collectors.browser_history import browser_collector, detect_browsers

router = APIRouter(prefix="/api/browsers", tags=["browsers"])


class EnabledBrowsersRequest(BaseModel):
    names: list[str] = Field(default_factory=list)


class ExcludedDomainsRequest(BaseModel):
    domains: list[str] = Field(default_factory=list)


@router.get("/status")
def get_status(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Return detected browsers, which are enabled, exclusions, and status."""
    detected = detect_browsers()
    enabled = set(tracking_config.get_enabled_browser_names())
    for b in detected:
        b["enabled"] = b["name"] in enabled
    return {
        "collector": browser_collector.status(),
        "browsers": detected,
        "excluded_domains": tracking_config.get_excluded_domains(),
    }


@router.post("/enabled")
def set_enabled(
    body: EnabledBrowsersRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Set the list of enabled browser names and reload the collector."""
    # Only persist names that are actually detected.
    detected_names = {b["name"] for b in detect_browsers()}
    valid = [n for n in body.names if n in detected_names]
    tracking_config.set_enabled_browser_names(valid)
    browser_collector.restart()
    return {
        "status": "ok",
        "enabled": valid,
        "collector": browser_collector.status(),
    }


@router.post("/excluded-domains")
def set_excluded_domains(
    body: ExcludedDomainsRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Update the excluded-domain list."""
    cleaned = [d.strip().lower() for d in body.domains if d.strip()]
    tracking_config.set_excluded_domains(cleaned)
    return {"status": "ok", "excluded_domains": cleaned}


@router.post("/start")
def start(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    browser_collector.restart()
    return {"status": "ok", "collector": browser_collector.status()}


@router.post("/stop")
def stop(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    browser_collector.stop()
    return {"status": "ok", "collector": browser_collector.status()}
