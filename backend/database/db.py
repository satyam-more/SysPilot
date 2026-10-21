"""
SQLite database initialisation and connection management.

Single file-based SQLite database at ~/.config/syspilot/syspilot.db
All writes go through _transaction() in events.py for atomicity.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_DIR = Path.home() / ".config" / "syspilot"
_DB_PATH = _DB_DIR / "syspilot.db"

# Module-level connection (one per process — SQLite is single-writer).
_conn: sqlite3.Connection | None = None


def get_db_path() -> Path:
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _conn


def init_db() -> sqlite3.Connection:
    """
    Create the database directory and file if they don't exist,
    run the schema migrations, and return the connection.
    Safe to call multiple times — idempotent.
    """
    global _conn

    _DB_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(_DB_PATH),
        check_same_thread=False,
        isolation_level=None,  # autocommit off — we manage transactions manually
    )
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better read/write concurrency.
    conn.execute("PRAGMA journal_mode=WAL")
    # Enforce foreign keys.
    conn.execute("PRAGMA foreign_keys=ON")

    _run_migrations(conn)
    _conn = conn
    logger.info("Database initialised at %s", _DB_PATH)
    return conn


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist. Order matters for FK constraints."""

    conn.executescript("""
        BEGIN;

        -- Core events table
        CREATE TABLE IF NOT EXISTS events (
            id              TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL,          -- ISO 8601 UTC e.g. 2026-10-17T14:23:00+00:00
            source          TEXT NOT NULL,           -- filesystem | terminal | shell
            event_type      TEXT NOT NULL,           -- file_modified | command_run | ...
            evidence_type   TEXT NOT NULL DEFAULT 'observed',  -- observed | inferred
            privacy_status  TEXT NOT NULL DEFAULT 'permitted', -- permitted | redacted
            file_path       TEXT,
            title           TEXT,
            content_excerpt TEXT,
            metadata        TEXT,                   -- JSON blob for extra fields
            created_at      TEXT NOT NULL
        );

        -- Full-text search index (explicit paired writes — no hidden triggers)
        -- Regular FTS5 table: stores id, title, content_excerpt directly.
        -- We manage inserts/deletes manually alongside the events table.
        CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
            id,
            title,
            content_excerpt
        );

        -- Privacy settings
        CREATE TABLE IF NOT EXISTS privacy_settings (
            id              INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
            mode            TEXT NOT NULL DEFAULT 'active',
            updated_at      TEXT NOT NULL
        );

        -- API provider config (key_ref only — actual key in OS keyring)
        CREATE TABLE IF NOT EXISTS provider_config (
            id              INTEGER PRIMARY KEY CHECK (id = 1),
            provider_name   TEXT NOT NULL DEFAULT 'openai',
            model           TEXT,           -- selected model name
            key_ref         TEXT,           -- opaque ref passed to keystore
            persistent      INTEGER,        -- 1=OS keyring, 0=session only
            updated_at      TEXT NOT NULL
        );

        -- Directories the filesystem collector watches.
        CREATE TABLE IF NOT EXISTS watched_directories (
            path            TEXT PRIMARY KEY,
            added_at        TEXT NOT NULL
        );

        -- Simple key/value settings (excluded extensions, folders, etc.).
        CREATE TABLE IF NOT EXISTS tracking_settings (
            key             TEXT PRIMARY KEY,
            value           TEXT NOT NULL
        );

        COMMIT;
    """)

    # Lightweight migration: add provider_config.model to pre-existing DBs.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(provider_config)")}
    if "model" not in cols:
        conn.execute("ALTER TABLE provider_config ADD COLUMN model TEXT")
