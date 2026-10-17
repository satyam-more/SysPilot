"""
Browser-history collector (plugin-style, no browser extension).

Reads the local history SQLite file of Chromium-based browsers and Firefox,
records new page visits as events, and polls periodically for new ones.

Because browsers lock the live history file, we copy it to a temp file before
reading. Only NEW visits (since the last recorded timestamp) are ingested, so
re-polling does not duplicate events.

Domain exclusions let the user keep private sites (banking, etc.) out.
Privacy mode is enforced by ingest_event(); the collector also registers
stop/status callbacks so polling halts on privacy activation.
"""

import logging
import shutil
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from backend.collectors import tracking_config
from backend.memory.events import ingest_event
from backend.memory.models import EventCreate

logger = logging.getLogger(__name__)

# How often to poll browser history (seconds). History isn't time-critical.
_POLL_INTERVAL = 60.0

# Known Chromium-based browsers: name -> history path (relative to $HOME).
_CHROMIUM_BROWSERS: dict[str, str] = {
    "Google Chrome": ".config/google-chrome/Default/History",
    "Chromium": ".config/chromium/Default/History",
    "Brave": ".config/BraveSoftware/Brave-Browser/Default/History",
    "Microsoft Edge": ".config/microsoft-edge/Default/History",
    "Vivaldi": ".config/vivaldi/Default/History",
    "Opera": ".config/opera/History",
}


def _home() -> Path:
    return Path.home()


def detect_browsers() -> list[dict]:
    """
    Return a list of installed browsers found on this machine.
    Each entry: {"name": str, "path": str, "kind": "chromium"|"firefox"}.
    """
    found: list[dict] = []

    for name, rel in _CHROMIUM_BROWSERS.items():
        p = _home() / rel
        if p.is_file():
            found.append({"name": name, "path": str(p), "kind": "chromium"})

    # Firefox: scan profiles for places.sqlite
    ff_dir = _home() / ".mozilla" / "firefox"
    if ff_dir.is_dir():
        for profile in ff_dir.glob("*.default*"):
            places = profile / "places.sqlite"
            if places.is_file():
                found.append(
                    {"name": f"Firefox ({profile.name})", "path": str(places), "kind": "firefox"}
                )

    return found


def _chromium_ts_to_dt(webkit_ts: int) -> datetime:
    """Chromium stores microseconds since 1601-01-01 UTC."""
    # 11644473600 seconds between 1601-01-01 and 1970-01-01.
    unix_seconds = webkit_ts / 1_000_000 - 11644473600
    return datetime.fromtimestamp(max(0, unix_seconds), tz=timezone.utc)


def _firefox_ts_to_dt(moz_ts: int) -> datetime:
    """Firefox stores microseconds since 1970-01-01 UTC."""
    return datetime.fromtimestamp(moz_ts / 1_000_000, tz=timezone.utc)


# Auth/redirect/account hosts that leak sensitive titles and add no signal.
# Matched as substrings of the hostname (covers regional TLDs like .co.in).
_NOISE_HOST_SUBSTRINGS = [
    "accounts.google.",
    "accounts.youtube.",
    "login.",
    "signin",
    "oauth",
    "auth.",
]

# URL path fragments that indicate a redirect/auth hop, not a real page visit.
_NOISE_PATH_SUBSTRINGS = [
    "/setsid",
    "/accounts/",
    "/o/oauth2",
    "/signin",
]


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_excluded(url: str, excluded_domains: list[str]) -> bool:
    host = _domain(url)
    if not host:
        return True  # unparseable — skip

    # Always skip auth/redirect/noise hosts — they carry sensitive titles
    # (e.g. inbox counts) and no useful activity signal.
    for noise in _NOISE_HOST_SUBSTRINGS:
        if noise in host:
            return True

    # Skip auth/redirect paths regardless of host.
    try:
        path = (urlparse(url).path or "").lower()
        for np in _NOISE_PATH_SUBSTRINGS:
            if np in path:
                return True
    except Exception:
        return True

    for ex in excluded_domains:
        ex = ex.lower().strip()
        if ex and (host == ex or host.endswith("." + ex)):
            return True
    return False


def _read_chromium_visits(db_copy: str, since_ts: int) -> list[tuple]:
    """Return (url, title, last_visit_webkit_ts) rows newer than since_ts."""
    conn = sqlite3.connect(db_copy)
    try:
        rows = conn.execute(
            "SELECT url, title, last_visit_time FROM urls "
            "WHERE last_visit_time > ? ORDER BY last_visit_time ASC LIMIT 500",
            (since_ts,),
        ).fetchall()
    finally:
        conn.close()
    return rows


def _read_firefox_visits(db_copy: str, since_ts: int) -> list[tuple]:
    conn = sqlite3.connect(db_copy)
    try:
        rows = conn.execute(
            "SELECT p.url, p.title, p.last_visit_date FROM moz_places p "
            "WHERE p.last_visit_date > ? AND p.last_visit_date IS NOT NULL "
            "ORDER BY p.last_visit_date ASC LIMIT 500",
            (since_ts,),
        ).fetchall()
    finally:
        conn.close()
    return rows


class BrowserHistoryCollector:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        # Per-browser high-water mark of the last visit timestamp we recorded.
        self._last_ts: dict[str, int] = {}

    def _poll_once(self) -> int:
        """Poll all enabled browsers once. Returns number of events recorded."""
        enabled = tracking_config.list_enabled_browsers()
        excluded = tracking_config.get_excluded_domains()
        recorded = 0

        for browser in enabled:
            name = browser["name"]
            path = browser["path"]
            kind = browser["kind"]
            src = Path(path)
            if not src.is_file():
                continue

            since = self._last_ts.get(name, self._default_since(kind))

            # Copy the locked DB to a temp file before reading.
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp_path = tmp.name
            tmp.close()
            try:
                shutil.copy2(src, tmp_path)
                if kind == "chromium":
                    rows = _read_chromium_visits(tmp_path, since)
                    ts_to_dt = _chromium_ts_to_dt
                else:
                    rows = _read_firefox_visits(tmp_path, since)
                    ts_to_dt = _firefox_ts_to_dt
            except (sqlite3.Error, OSError) as exc:
                logger.warning("Could not read %s history: %s", name, exc)
                continue
            finally:
                try:
                    Path(tmp_path).unlink()
                except OSError:
                    pass

            max_ts = since
            seen_titles: set[str] = set()
            for url, title, raw_ts in rows:
                if raw_ts and raw_ts > max_ts:
                    max_ts = raw_ts
                if _is_excluded(url, excluded):
                    continue
                # Dedup: one event per distinct title per poll (editors/tabs
                # produce many URL variants of the same page).
                norm_title = (title or _domain(url)).strip().lower()
                if not norm_title or norm_title in seen_titles:
                    continue
                seen_titles.add(norm_title)
                try:
                    visited = ts_to_dt(raw_ts) if raw_ts else datetime.now(timezone.utc)
                    event = EventCreate(
                        source="browser",
                        event_type="page_visited",
                        title=(title or _domain(url))[:512],
                        content_excerpt=f"Visited {_domain(url)} — {(title or '')[:120]}",
                        metadata={"url": url, "browser": name, "visited_at": visited.isoformat()},
                        evidence_type="observed",
                    )
                    if ingest_event(event) is not None:
                        recorded += 1
                except Exception as exc:  # noqa: BLE001 — never crash the poller
                    logger.debug("Skipped a browser visit: %s", exc)

            self._last_ts[name] = max_ts

        return recorded

    def _default_since(self, kind: str) -> int:
        """On first run, only record visits from the last 7 days (avoid a flood)."""
        now = datetime.now(timezone.utc).timestamp()
        seven_days_ago = now - 7 * 86400
        if kind == "chromium":
            return int((seven_days_ago + 11644473600) * 1_000_000)
        return int(seven_days_ago * 1_000_000)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                n = self._poll_once()
                if n:
                    logger.info("Browser collector recorded %d new visit(s).", n)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Browser poll failed: %s", exc)
            self._stop_event.wait(_POLL_INTERVAL)

    def start(self) -> None:
        if self._running:
            return
        if not tracking_config.list_enabled_browsers():
            logger.info("Browser collector: no browsers enabled.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._running = True
        logger.info("Browser history collector started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._running = False
        logger.info("Browser history collector stopped.")

    def restart(self) -> None:
        self.stop()
        self.start()

    def status(self) -> str:
        return "running" if self._running else "stopped"


browser_collector = BrowserHistoryCollector()
