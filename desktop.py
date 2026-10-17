"""
TrailBack desktop launcher.

Starts the FastAPI backend on a loopback port in a background thread,
waits for it to become healthy, then opens a native desktop window
pointing at it via pywebview.

Because the backend serves the React frontend same-origin and injects the
session token into index.html, there is no CORS / dev-token race here —
the window loads a fully authenticated page.

Run:
    .venv/bin/python desktop.py
"""

import logging
import socket
import threading
import time
from contextlib import closing

import httpx
import uvicorn
import webview

from backend.main import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trailback.desktop")

HOST = "127.0.0.1"


def _find_free_port() -> int:
    """Pick an available loopback port."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _run_backend(port: int) -> None:
    """Run uvicorn in this thread (called from a daemon thread)."""
    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server.run()


def _wait_for_health(port: int, timeout: float = 15.0) -> bool:
    """Poll /health until the backend responds or the timeout elapses."""
    url = f"http://{HOST}:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    return False


def main() -> None:
    port = _find_free_port()
    logger.info("Starting TrailBack backend on %s:%d", HOST, port)

    # Register the WebView's own origin so same-origin requests from the
    # desktop window pass the Origin allowlist check.
    from backend.api.auth import register_origin
    register_origin(f"http://{HOST}:{port}")
    register_origin(f"http://localhost:{port}")

    backend_thread = threading.Thread(
        target=_run_backend, args=(port,), daemon=True
    )
    backend_thread.start()

    if not _wait_for_health(port):
        logger.error("Backend did not become healthy in time. Exiting.")
        return

    logger.info("Backend ready. Opening desktop window.")

    webview.create_window(
        title="TrailBack",
        url=f"http://{HOST}:{port}/",
        width=1100,
        height=760,
        min_size=(800, 600),
    )
    # GUI backend is chosen automatically; Qt6 WebEngine is installed in the venv.
    webview.start(gui="qt")


if __name__ == "__main__":
    main()
