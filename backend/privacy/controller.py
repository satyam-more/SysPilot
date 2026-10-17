"""
Privacy controller — authoritative gate for event recording.

PrivacyController is a process-level singleton. activate_privacy() sets
the internal state to "paused" synchronously (step 1) before writing the
shell-side file or notifying collectors (steps 2–3). This means
is_recording_permitted() returns False immediately after activation,
with no race window at the ingestion layer.

Usage:
    from backend.privacy.controller import privacy_controller

    if not privacy_controller.is_recording_permitted(source):
        return None  # drop the event
"""

import logging
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_PRIVACY_FILE = Path.home() / ".config" / "trailback" / "privacy_active"


class PrivacyController:
    _instance: "PrivacyController | None" = None
    _class_lock = threading.Lock()

    def __new__(cls) -> "PrivacyController":
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._state = "active"
                    inst._collectors: dict[str, tuple[Callable, Callable]] = {}
                    inst._privacy_file = _PRIVACY_FILE
                    cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_recording_permitted(self, source: str = "") -> bool:
        """
        Called by event ingestion before every DB write.
        Returns False immediately when paused — no I/O, no locks.
        """
        return self._state == "active"

    def activate_privacy(self) -> dict:
        """
        Atomic 3-step transition to paused state:
          1. Set _state = "paused"  ← ingestion gate fires from this point
          2. Write privacy_active file for shell hook optimisation
          3. Notify registered collectors to stop

        Returns per-collector acknowledgment dict.
        """
        # Step 1 — authoritative change (synchronous)
        self._state = "paused"
        logger.info("Privacy mode activated.")

        # Step 2 — client-side optimisation for shell hook
        try:
            self._privacy_file.parent.mkdir(parents=True, exist_ok=True)
            self._privacy_file.touch()
        except OSError as exc:
            logger.warning("Could not write privacy_active file: %s", exc)

        # Step 3 — notify collectors
        results: dict[str, str] = {}
        for name, (stop_fn, status_fn) in self._collectors.items():
            try:
                stop_fn()
                results[name] = status_fn()
            except Exception as exc:
                logger.warning("Collector %r stop failed: %s", name, exc)
                results[name] = "error"

        return {"state": self._state, "collectors": results}

    def deactivate_privacy(self) -> None:
        """Resume recording and remove the privacy_active file."""
        self._state = "active"
        logger.info("Privacy mode deactivated.")
        try:
            if self._privacy_file.exists():
                self._privacy_file.unlink()
        except OSError as exc:
            logger.warning("Could not remove privacy_active file: %s", exc)

    def register_collector(
        self,
        name: str,
        stop_fn: Callable,
        status_fn: Callable,
    ) -> None:
        """Register a collector's stop and status callbacks."""
        self._collectors[name] = (stop_fn, status_fn)

    def get_status(self) -> dict:
        collector_status = {}
        for name, (_, status_fn) in self._collectors.items():
            try:
                collector_status[name] = status_fn()
            except Exception:
                collector_status[name] = "error"
        return {"state": self._state, "collectors": collector_status}

    # Allow tests to reset the singleton
    @classmethod
    def _reset(cls) -> None:
        cls._instance = None


# Module-level singleton — always import this, never instantiate directly.
privacy_controller = PrivacyController()
