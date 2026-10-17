"""
Event query operations: search, delete, update.

All writes use _transaction() from events.py to keep events and
events_fts in sync. Deleted content must not remain searchable.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from backend.database.db import get_connection
from backend.memory.events import _transaction
from backend.memory.models import Event

logger = logging.getLogger(__name__)


def _row_to_event(row) -> Event:
    """Convert a sqlite3.Row to an Event model."""
    d = dict(row)
    if d.get("metadata"):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except (ValueError, TypeError):
            d["metadata"] = None
    return Event.model_validate(d)


def search_events(
    query: str,
    limit: int = 10,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    source: Optional[str] = None,
) -> list[Event]:
    """
    Full-text search over permitted events only.

    The privacy_status = 'permitted' filter is defence-in-depth: even if an
    event were incorrectly written without the privacy gate, it won't surface
    in search results.
    """
    conn = get_connection()

    # FTS5 MATCH must reference the virtual table by name (not alias).
    # We get matching IDs first, then fetch full event rows.
    fts_params: list = [query]
    fts_conditions = ["events_fts MATCH ?"]

    extra_conditions = ["e.privacy_status = 'permitted'"]
    extra_params: list = []

    if start_time:
        extra_conditions.append("e.timestamp >= ?")
        extra_params.append(start_time.isoformat())
    if end_time:
        extra_conditions.append("e.timestamp <= ?")
        extra_params.append(end_time.isoformat())
    if source:
        extra_conditions.append("e.source = ?")
        extra_params.append(source)

    sql = f"""
        SELECT e.*
        FROM events e
        WHERE e.id IN (
            SELECT id FROM events_fts
            WHERE {' AND '.join(fts_conditions)}
            ORDER BY rank
            LIMIT ?
        )
        AND {' AND '.join(extra_conditions)}
        ORDER BY e.timestamp DESC
    """

    params = fts_params + [limit] + extra_params
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_event(r) for r in rows]


def get_event(event_id: str) -> Event | None:
    """Fetch a single event by id. Returns None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    return _row_to_event(row) if row else None


def delete_event(event_id: str) -> bool:
    """
    Delete an event and its FTS entry atomically.
    Returns True if a row was deleted, False if not found.
    Deleted content must not remain searchable — both rows removed in one
    transaction.
    """
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if not existing:
        return False

    with _transaction() as txn:
        txn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        txn.execute("DELETE FROM events_fts WHERE id = ?", (event_id,))

    return True


def update_event_excerpt(event_id: str, new_excerpt: str) -> bool:
    """
    Update the content_excerpt of an event and sync the FTS index.
    Both writes happen in one transaction — no stale FTS entries.
    Returns True if the event was found and updated, False otherwise.
    """
    conn = get_connection()
    existing = conn.execute(
        "SELECT id, title FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if not existing:
        return False

    with _transaction() as txn:
        txn.execute(
            "UPDATE events SET content_excerpt = ? WHERE id = ?",
            (new_excerpt, event_id),
        )
        # Update FTS: delete old entry, insert new one.
        txn.execute("DELETE FROM events_fts WHERE id = ?", (event_id,))
        txn.execute(
            "INSERT INTO events_fts (id, title, content_excerpt) VALUES (?, ?, ?)",
            (event_id, existing["title"] or "", new_excerpt),
        )

    return True


def list_events(
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
) -> list[Event]:
    """List permitted events in reverse chronological order."""
    conn = get_connection()
    conditions = ["privacy_status = 'permitted'"]
    params: list = []

    if source:
        conditions.append("source = ?")
        params.append(source)

    params.extend([limit, offset])
    sql = f"""
        SELECT * FROM events
        WHERE {' AND '.join(conditions)}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_event(r) for r in rows]
