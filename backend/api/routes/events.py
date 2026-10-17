"""
Event ingestion and query routes.

POST /api/events           — ingest an event (shell collector, shell token auth)
GET  /api/events           — list recent permitted events (browser auth)
GET  /api/events/{id}      — fetch a single event (browser auth)
DELETE /api/events/{id}    — delete an event and its FTS entry (browser auth)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.auth import validate_browser_request, validate_shell_request
from backend.memory.events import ingest_event
from backend.memory.models import Event, EventCreate
from backend.memory.search import delete_event, get_event, list_events

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("", status_code=201)
def ingest(
    event: EventCreate,
    _auth: None = Depends(validate_shell_request),
) -> dict:
    """
    Ingest an event from a collector (shell hook, filesystem watcher).
    Returns 201 on success, 200 with dropped=true if privacy mode is active.
    """
    result = ingest_event(event)
    if result is None:
        return {"status": "dropped", "reason": "privacy_mode_active"}
    return {"status": "ok", "id": result.id}


@router.get("")
def list_recent(
    request: Request,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    _auth: None = Depends(validate_browser_request),
) -> list[Event]:
    """List permitted events in reverse chronological order."""
    return list_events(limit=limit, offset=offset, source=source)


@router.get("/{event_id}")
def fetch_event(
    event_id: str,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> Event:
    """Fetch a single event by id."""
    ev = get_event(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return ev


@router.delete("/{event_id}", status_code=204)
def remove_event(
    event_id: str,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> None:
    """Delete an event and its FTS index entry atomically."""
    deleted = delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
