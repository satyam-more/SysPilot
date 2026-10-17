"""
Event ingestion layer.

ingest_event() is the single entry point for all collectors.
It checks the privacy gate before opening any DB transaction — no event
persists during or after a privacy activation.

The _transaction() context manager ensures events and events_fts are always
written together. A failure in either write rolls back both.
"""

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from backend.database.db import get_connection
from backend.memory.models import Event, EventCreate

logger = logging.getLogger(__name__)


@contextmanager
def _transaction() -> Generator[sqlite3.Connection, None, None]:
    """
    Yield a connection inside an explicit BEGIN/COMMIT block.
    Rolls back automatically if an exception is raised.
    """
    conn = get_connection()
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def ingest_event(event: EventCreate) -> Event | None:
    """
    Persist a single event.

    Returns the created Event on success, or None if recording is not
    currently permitted (privacy mode active).

    The privacy check happens BEFORE the transaction is opened so that
    no DB work is done at all when privacy is active.
    """
    # Import here to avoid circular imports at module load time.
    from backend.privacy.controller import privacy_controller

    # Authoritative gate — synchronous in-memory check, no race window.
    if not privacy_controller.is_recording_permitted(event.source):
        logger.debug("Event from %r dropped — privacy mode active.", event.source)
        return None

    row = Event(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        privacy_status="permitted",
        created_at=datetime.now(timezone.utc),
        **event.model_dump(),
    )

    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO events (
                id, timestamp, source, event_type, evidence_type,
                privacy_status, file_path, title, content_excerpt,
                metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.id,
                row.timestamp.isoformat(),
                row.source,
                row.event_type,
                row.evidence_type,
                row.privacy_status,
                row.file_path,
                row.title,
                row.content_excerpt,
                json.dumps(row.metadata) if row.metadata else None,
                row.created_at.isoformat(),
            ),
        )
        # Paired FTS write — must succeed or the whole transaction rolls back.
        conn.execute(
            "INSERT INTO events_fts (id, title, content_excerpt) VALUES (?, ?, ?)",
            (row.id, row.title or "", row.content_excerpt or ""),
        )

    return row
