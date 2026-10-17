"""
Filesystem collector.

Watches user-configured directories with watchdog. On file create/modify/
delete, builds an EventCreate and calls ingest_event(). Exclusions (folders,
extensions) are applied before an event is built. Privacy mode is enforced by
ingest_event() itself, but the collector also registers stop/status callbacks
with the privacy controller so the observer halts on privacy activation.

Runs in a background thread started at app startup.
"""

import logging
import os
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backend.collectors.tracking_config import (
    get_excluded_extensions,
    get_excluded_folders,
    list_watched_directories,
)
from backend.memory.events import ingest_event
from backend.memory.models import EventCreate

logger = logging.getLogger(__name__)

# Debounce: editors fire many modify events per save. Collapse repeats to the
# same path within this window into a single event.
_DEBOUNCE_SECONDS = 2.0


class _Handler(FileSystemEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def _should_skip(self, path: str) -> bool:
        p = Path(path)
        # Skip directories themselves (we care about files).
        if p.is_dir():
            return True
        # Skip excluded folders anywhere in the path.
        parts = set(p.parts)
        for folder in get_excluded_folders():
            if folder in parts:
                return True
        # Skip excluded extensions / suffixes.
        name = p.name
        for ext in get_excluded_extensions():
            if name.endswith(ext):
                return True
        return False

    def _debounced(self, path: str) -> bool:
        """Return True if this path was seen too recently (skip it)."""
        now = time.monotonic()
        with self._lock:
            last = self._last_seen.get(path, 0.0)
            if now - last < _DEBOUNCE_SECONDS:
                return True
            self._last_seen[path] = now
        return False

    def _emit(self, path: str, event_type: str) -> None:
        if self._should_skip(path):
            return
        if self._debounced(path):
            return
        p = Path(path)
        try:
            event = EventCreate(
                source="filesystem",
                event_type=event_type,
                file_path=str(p),
                title=p.name,
                content_excerpt=f"{event_type.replace('_', ' ')}: {p.name} in {p.parent}",
                evidence_type="observed",
            )
            # ingest_event enforces the privacy gate; returns None if paused.
            ingest_event(event)
        except Exception as exc:  # noqa: BLE001 — never crash the watcher thread
            logger.warning("Failed to record filesystem event for %s: %s", path, exc)

    # watchdog callbacks ----------------------------------------------------
    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(event.src_path, "file_created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(event.src_path, "file_modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(event.src_path, "file_deleted")


class FilesystemCollector:
    def __init__(self) -> None:
        self._observer: Observer | None = None
        self._handler = _Handler()
        self._running = False

    def start(self) -> None:
        """Start watching all configured directories. Safe to call repeatedly."""
        if self._running:
            return
        dirs = list_watched_directories()
        if not dirs:
            logger.info("Filesystem collector: no watched directories configured.")
            return

        self._observer = Observer()
        watched = 0
        for d in dirs:
            if os.path.isdir(d):
                self._observer.schedule(self._handler, d, recursive=True)
                watched += 1
            else:
                logger.warning("Watched directory does not exist, skipping: %s", d)

        if watched == 0:
            self._observer = None
            logger.info("Filesystem collector: no valid directories to watch.")
            return

        self._observer.start()
        self._running = True
        logger.info("Filesystem collector started on %d director(ies).", watched)

    def stop(self) -> None:
        """Stop the observer. Used by the privacy controller."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
        self._running = False
        logger.info("Filesystem collector stopped.")

    def restart(self) -> None:
        """Reload the watched-directory list (call after config changes)."""
        self.stop()
        self.start()

    def status(self) -> str:
        return "running" if self._running else "stopped"


# Module-level singleton.
filesystem_collector = FilesystemCollector()
