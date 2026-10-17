"""
Tracking API routes.

Manage which directories the filesystem collector watches and the
folder/extension exclusions. Starting/stopping the collector reloads
the watch list.

All mutable endpoints require browser auth (Origin + session token).
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.auth import validate_browser_request
from backend.collectors import tracking_config
from backend.collectors.filesystem import filesystem_collector

router = APIRouter(prefix="/api/tracking", tags=["tracking"])


class WatchedDirRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class ExclusionsRequest(BaseModel):
    folders: list[str] | None = None
    extensions: list[str] | None = None


@router.get("/status")
def get_status(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Return collector status, watched dirs, and current exclusions."""
    return {
        "collector": filesystem_collector.status(),
        "watched_directories": tracking_config.list_watched_directories(),
        "excluded_folders": tracking_config.get_excluded_folders(),
        "excluded_extensions": tracking_config.get_excluded_extensions(),
    }


@router.post("/directories")
def add_directory(
    body: WatchedDirRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Add a directory to watch. Must be an existing directory."""
    path = os.path.expanduser(body.path.strip())
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Path is not an existing directory")
    tracking_config.add_watched_directory(path)
    # Reload the collector so the new directory is watched immediately.
    filesystem_collector.restart()
    return {
        "status": "ok",
        "watched_directories": tracking_config.list_watched_directories(),
        "collector": filesystem_collector.status(),
    }


@router.delete("/directories")
def remove_directory(
    body: WatchedDirRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Stop watching a directory."""
    path = os.path.expanduser(body.path.strip())
    tracking_config.remove_watched_directory(path)
    filesystem_collector.restart()
    return {
        "status": "ok",
        "watched_directories": tracking_config.list_watched_directories(),
        "collector": filesystem_collector.status(),
    }


@router.post("/exclusions")
def set_exclusions(
    body: ExclusionsRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Update excluded folders and/or extensions."""
    if body.folders is not None:
        tracking_config.set_excluded_folders(body.folders)
    if body.extensions is not None:
        tracking_config.set_excluded_extensions(body.extensions)
    return {
        "status": "ok",
        "excluded_folders": tracking_config.get_excluded_folders(),
        "excluded_extensions": tracking_config.get_excluded_extensions(),
    }


@router.post("/start")
def start_collector(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Start (or reload) the filesystem collector."""
    filesystem_collector.restart()
    return {"status": "ok", "collector": filesystem_collector.status()}


@router.post("/stop")
def stop_collector(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    """Stop the filesystem collector."""
    filesystem_collector.stop()
    return {"status": "ok", "collector": filesystem_collector.status()}
