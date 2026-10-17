"""
POST /api/ask — main question-answering endpoint.

Privacy gate: if privacy mode is active, returns 403 before the agent
loop is started. No event content is accessed while privacy is active.

Auth: requires valid Origin + session token (browser request).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.auth import validate_browser_request
from backend.privacy.controller import privacy_controller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ask"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AskContextHint(BaseModel):
    """Optional structured hint to narrow the agent's search."""
    time_range: Optional[str] = Field(
        default=None,
        description="Natural language time range e.g. 'last 2 hours', 'yesterday'",
    )
    source: Optional[str] = Field(
        default=None,
        description="Limit context to a specific source: filesystem | terminal | shell",
    )
    keywords: Optional[list[str]] = Field(
        default=None,
        max_length=10,
        description="Keywords to pre-seed the search with",
    )


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    context_hint: Optional[AskContextHint] = None


class SourceLink(BaseModel):
    event_id: str
    source: str
    title: Optional[str]
    timestamp: str
    excerpt: Optional[str]


class EvidenceItem(BaseModel):
    event_id: str
    source: str
    event_type: str
    title: Optional[str]
    timestamp: str
    content_excerpt: Optional[str]


class AskResponse(BaseModel):
    answer: str
    evidence: list[EvidenceItem]
    iterations: int
    tool_calls_made: int


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> Any:
    """
    Answer a natural language question about the user's recent activity.

    Privacy gate fires before any DB access — returns 403 if active.
    The agent loop calls search_events/list_events tools internally.
    """
    # Privacy gate — checked before the loop starts.
    if not privacy_controller.is_recording_permitted():
        raise HTTPException(
            status_code=403,
            detail="Privacy mode is active. Disable it before querying activity.",
        )

    # Build a context hint string for the loop if provided.
    context_hint_str: Optional[str] = None
    if body.context_hint:
        parts = []
        if body.context_hint.time_range:
            parts.append(f"Time range: {body.context_hint.time_range}")
        if body.context_hint.source:
            parts.append(f"Source filter: {body.context_hint.source}")
        if body.context_hint.keywords:
            parts.append(f"Keywords: {', '.join(body.context_hint.keywords)}")
        if parts:
            context_hint_str = "; ".join(parts)

    try:
        from backend.harness.loop import run_agent_loop
        result = run_agent_loop(
            user_question=body.question,
            context_hint=context_hint_str,
        )
    except RuntimeError as exc:
        logger.error("Agent loop failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # Map evidence dicts to EvidenceItem models.
    evidence = []
    for ev in result.get("evidence", []):
        evidence.append(EvidenceItem(
            event_id=ev.get("id", ""),
            source=ev.get("source", ""),
            event_type=ev.get("event_type", ""),
            title=ev.get("title"),
            timestamp=str(ev.get("timestamp", "")),
            content_excerpt=ev.get("content_excerpt"),
        ))

    return AskResponse(
        answer=result["answer"],
        evidence=evidence,
        iterations=result["iterations"],
        tool_calls_made=len(result.get("tool_calls", [])),
    )
