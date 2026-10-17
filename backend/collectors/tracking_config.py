"""
Tracking configuration — which directories the filesystem collector watches
and which files/folders to exclude.

Stored in the watched_directories and tracking_settings tables.
"""

import json
import logging
from datetime import datetime, timezone

from backend.database.db import get_connection
from backend.memory.events import _transaction

logger = logging.getLogger(__name__)

# Sensible defaults: never record noise from build/VCS/cache folders.
_DEFAULT_EXCLUDED_FOLDERS = [
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
    "build", "target", ".cache", ".idea", ".vscode", "site-packages",
]

# Temp/lock/binary extensions that carry no useful activity signal.
_DEFAULT_EXCLUDED_EXTENSIONS = [
    ".tmp", ".swp", ".swx", ".lock", ".pyc", ".pyo", ".log", ".o",
    ".class", ".DS_Store", "~",
]


def list_watched_directories() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT path FROM watched_directories ORDER BY path"
    ).fetchall()
    return [r["path"] for r in rows]


def add_watched_directory(path: str) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with _transaction() as txn:
        txn.execute(
            "INSERT OR IGNORE INTO watched_directories (path, added_at) VALUES (?, ?)",
            (path, now),
        )
    logger.info("Now watching directory: %s", path)


def remove_watched_directory(path: str) -> None:
    conn = get_connection()
    with _transaction() as txn:
        txn.execute("DELETE FROM watched_directories WHERE path = ?", (path,))
    logger.info("Stopped watching directory: %s", path)


def _get_setting(key: str, default: list[str]) -> list[str]:
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM tracking_settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return list(default)
    try:
        return json.loads(row["value"])
    except (ValueError, TypeError):
        return list(default)


def _set_setting(key: str, value: list[str]) -> None:
    conn = get_connection()
    with _transaction() as txn:
        txn.execute(
            "INSERT INTO tracking_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def get_excluded_folders() -> list[str]:
    return _get_setting("excluded_folders", _DEFAULT_EXCLUDED_FOLDERS)


def get_excluded_extensions() -> list[str]:
    return _get_setting("excluded_extensions", _DEFAULT_EXCLUDED_EXTENSIONS)


def set_excluded_folders(folders: list[str]) -> None:
    _set_setting("excluded_folders", folders)


def set_excluded_extensions(exts: list[str]) -> None:
    _set_setting("excluded_extensions", exts)
