"""
Tests for event ingestion and search.
"""

import os
import pytest

from backend.database.db import init_db, get_connection
from backend.memory.events import ingest_event, _transaction
from backend.memory.models import EventCreate
from backend.memory.search import (
    delete_event,
    get_event,
    list_events,
    search_events,
    update_event_excerpt,
)
from backend.privacy.controller import PrivacyController


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Each test gets a fresh in-memory-like DB via a temp file."""
    import backend.database.db as db_mod
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_mod, "_DB_PATH", db_path)
    monkeypatch.setattr(db_mod, "_DB_DIR", tmp_path)
    monkeypatch.setattr(db_mod, "_conn", None)
    init_db()
    # Reset privacy controller
    PrivacyController._reset()
    yield
    conn = db_mod._conn
    if conn:
        conn.close()
    db_mod._conn = None
    PrivacyController._reset()


def make_event(**kwargs) -> EventCreate:
    defaults = {
        "source": "filesystem",
        "event_type": "file_modified",
        "title": "test.docx",
        "content_excerpt": "hello world",
    }
    defaults.update(kwargs)
    return EventCreate(**defaults)


class TestIngestEvent:
    def test_returns_event_with_timezone_aware_timestamp(self):
        result = ingest_event(make_event())
        assert result is not None
        assert result.timestamp.tzinfo is not None

    def test_writes_to_both_tables(self):
        ingest_event(make_event(content_excerpt="ownership rules"))
        conn = get_connection()
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM events_fts").fetchone()[0] == 1

    def test_privacy_gate_blocks_ingestion(self):
        PrivacyController._reset()
        c = PrivacyController()
        c.activate_privacy()
        result = ingest_event(make_event())
        assert result is None
        conn = get_connection()
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0

    def test_privacy_status_is_permitted(self):
        result = ingest_event(make_event())
        assert result.privacy_status == "permitted"

    def test_rollback_on_partial_failure(self):
        conn = get_connection()
        before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        # Force a failure by inserting invalid data mid-transaction
        try:
            with _transaction() as txn:
                txn.execute(
                    "INSERT INTO events (id, timestamp, source, event_type, "
                    "evidence_type, privacy_status, created_at) "
                    "VALUES (?, datetime('now'), 'filesystem', 'test', "
                    "'observed', 'permitted', datetime('now'))",
                    ("rollback-test-id",),
                )
                # Simulate FTS failure
                raise RuntimeError("simulated FTS failure")
        except RuntimeError:
            pass
        after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert after == before, "Rollback failed — orphan row in events table"


class TestSearchEvents:
    def test_finds_matching_event(self):
        ingest_event(make_event(content_excerpt="ownership rules and borrowing"))
        results = search_events("ownership")
        assert len(results) == 1

    def test_redacted_events_not_returned(self):
        ev = ingest_event(make_event(content_excerpt="secret project"))
        conn = get_connection()
        with _transaction() as txn:
            txn.execute(
                "UPDATE events SET privacy_status='redacted' WHERE id=?",
                (ev.id,),
            )
        results = search_events("secret")
        assert len(results) == 0

    def test_source_filter(self):
        ingest_event(make_event(source="filesystem", content_excerpt="cargo run"))
        ingest_event(make_event(source="shell", content_excerpt="cargo run"))
        results = search_events("cargo", source="shell")
        assert len(results) == 1
        assert results[0].source == "shell"


class TestDeleteEvent:
    def test_deletes_from_both_tables(self):
        ev = ingest_event(make_event(content_excerpt="to be deleted"))
        assert delete_event(ev.id) is True
        conn = get_connection()
        assert conn.execute("SELECT COUNT(*) FROM events WHERE id=?", (ev.id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM events_fts WHERE id=?", (ev.id,)).fetchone()[0] == 0

    def test_deleted_event_not_searchable(self):
        ev = ingest_event(make_event(content_excerpt="delete me please"))
        delete_event(ev.id)
        assert len(search_events("delete")) == 0

    def test_returns_false_for_nonexistent(self):
        assert delete_event("nonexistent-id") is False


class TestUpdateExcerpt:
    def test_updates_event_and_fts(self):
        ev = ingest_event(make_event(content_excerpt="old content"))
        update_event_excerpt(ev.id, "new content rust borrowing")
        results = search_events("rust borrowing")
        assert len(results) == 1
        fetched = get_event(ev.id)
        assert fetched.content_excerpt == "new content rust borrowing"

    def test_old_content_not_searchable_after_update(self):
        ev = ingest_event(make_event(content_excerpt="uniqueoldterm12345"))
        update_event_excerpt(ev.id, "completely different")
        assert len(search_events("uniqueoldterm12345")) == 0
