"""
TrailBack backend — FastAPI application entry point.

Run with:
    source .venv/bin/activate
    uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.api.auth import get_session_token, init_auth
from backend.api.routes.ask import router as ask_router
from backend.api.routes.events import router as events_router
from backend.api.routes.model_settings import router as model_router
from backend.api.routes.privacy import router as privacy_router
from backend.database.db import init_db
from backend.harness.providers import provider_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Initialise DB
    init_db()
    logger.info("Database ready.")

    # Load provider config from DB
    provider_registry._load_config()
    logger.info("Provider registry loaded.")

    # Initialise auth (writes shell token file)
    init_auth()
    token = get_session_token()
    logger.info("Session token generated (in-memory only).")
    logger.info("Shell token written to ~/.config/trailback/shell_token")
    # Print token to console for development — in production this would be
    # injected into the served HTML via <meta name="tb-session">.
    print(f"\n[TrailBack] Session token: {token}\n")

    yield

    # Shutdown — nothing to clean up for now
    logger.info("TrailBack shutting down.")


app = FastAPI(
    title="TrailBack",
    description="Local AI memory assistant API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — only allow localhost origins (matches _BROWSER_ORIGINS in auth.py)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Register routers
app.include_router(events_router)
app.include_router(privacy_router)
app.include_router(model_router)
app.include_router(ask_router)


@app.get("/api/dev-token")
def dev_token() -> dict:
    """
    Dev-only endpoint: returns the session token for the Vite dev server.
    In the desktop/production build, the token is injected via the
    <meta name="tb-session"> tag in the served index.html instead.
    """
    return {"token": get_session_token()}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "trailback"}


# ---------------------------------------------------------------------------
# Serve the built frontend (desktop / production mode)
# ---------------------------------------------------------------------------
# When frontend/dist exists (after `npm run build`), the backend serves the
# React app same-origin and injects the real session token into index.html.
# This removes the CORS/dev-token race entirely — the token is present in the
# HTML before any JS runs.

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _serve_index() -> HTMLResponse:
    """Read index.html and inject the session token into the meta tag."""
    index_path = _FRONTEND_DIST / "index.html"
    html = index_path.read_text(encoding="utf-8")
    token = get_session_token()
    # Replace the empty meta content with the real token.
    html = html.replace(
        '<meta name="tb-session" content="" id="tb-session-token" />',
        f'<meta name="tb-session" content="{token}" id="tb-session-token" />',
    )
    # Fallback for minified/reordered attributes.
    if f'content="{token}"' not in html:
        html = html.replace(
            'name="tb-session" content=""',
            f'name="tb-session" content="{token}"',
        )
    return HTMLResponse(content=html)


if _FRONTEND_DIST.exists():
    # Mount static assets (JS/CSS bundles) at /assets.
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/", response_class=HTMLResponse)
    def serve_root() -> HTMLResponse:
        return _serve_index()

    # SPA fallback — any non-API path returns index.html so client routing works.
    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def serve_spa(full_path: str) -> HTMLResponse:
        # Serve index for client routes; real missing assets 404 via StaticFiles.
        return _serve_index()

else:
    @app.get("/")
    def root() -> dict:
        return {
            "message": "TrailBack API is running. Frontend not built yet — "
            "run `npm run build` in frontend/. See /docs for endpoints."
        }
