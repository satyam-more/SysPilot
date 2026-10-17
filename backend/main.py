"""
TrailBack backend — FastAPI application entry point.

Run with:
    source .venv/bin/activate
    uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import get_session_token, init_auth
from backend.api.routes.ask import router as ask_router
from backend.api.routes.events import router as events_router
from backend.api.routes.privacy import router as privacy_router
from backend.database.db import init_db

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
app.include_router(ask_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "trailback"}


@app.get("/")
def root() -> dict:
    return {"message": "TrailBack API is running. See /docs for endpoints."}
