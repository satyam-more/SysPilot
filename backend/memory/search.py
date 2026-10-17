"""
Event query operations: search, delete, update.

All writes use _transaction() from events.py to keep events and
events_fts in sync. Deleted content must not remain searchable.
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional

from backend.database.db import get_connection
from backend.memory.events import _transaction
from backend.memory.models import Event

logger = logging.getLogger(__name__)

# Common words that add no search value and hurt recall if required.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "about", "did", "do", "does", "i", "my", "me", "was",
    "were", "is", "are", "what", "where", "when", "how", "why", "which",
    "that", "this", "it", "any", "some", "from", "into", "while", "running",
    "learn", "learning", "work", "working", "stop", "stopped", "encounter",
    "encountered", "fully", "master", "mastered",
}

# Match word characters only; drop punctuation that would break FTS5 syntax.
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _build_fts_query(raw_query: str) -> str:
    """
    Turn a free-text query into a safe FTS5 OR expression.

    - Extracts word tokens, strips punctuation (which can break FTS5 syntax).
    - Removes stopwords so the query focuses on meaningful terms.
    - Joins remaining terms with OR so events matching ANY key term surface,
      ranked by FTS5 relevance. Falls back to all tokens if everything was a
      stopword (so a query like "where" still returns something sensible).
    """
    tokens = _WORD_RE.findall(raw_query.lower())
    if not tokens:
        return ""
    meaningful = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    terms = meaningful or tokens
    # Quote each term to treat it as a literal (avoids FTS5 operator clashes).
    return " OR ".join(f'"{t}"' for t in terms)


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

    # Convert the free-text query into an FTS5 OR expression so a multi-word
    # query matches events containing ANY of the key terms (ranked by
    # relevance), instead of requiring all terms in one row (FTS5 default AND).
    fts_query = _build_fts_query(query)
    if not fts_query:
        return []

    # FTS5 MATCH must reference the virtual table by name (not alias).
    # We get matching IDs first, then fetch full event rows.
    fts_params: list = [fts_query]
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
