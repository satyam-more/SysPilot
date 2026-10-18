"""
System-agent REST routes for the web front end.

POST /api/sys/ask        — ask the system-health agent a question
POST /api/sys/confirm    — confirm & run a staged command (the approval gate)
GET  /api/sys/health     — quick read-only health snapshot (no model)

All require browser auth (Origin + session token).
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.api.auth import validate_browser_request
from backend.mcp_server import actions, diagnostics, sysagent

router = APIRouter(prefix="/api/sys", tags=["sysagent"])


class HistoryTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=12)


class ConfirmRequest(BaseModel):
    pending_id: str = Field(min_length=1, max_length=64)


@router.post("/ask")
async def ask(
    body: AskRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    history = [{"role": t.role, "content": t.content} for t in body.history]
    return await sysagent.run_system_agent(body.question, history=history)


@router.post("/confirm")
def confirm(
    body: ConfirmRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    return actions.confirm_and_apply(body.pending_id)


@router.get("/health")
def health(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    return diagnostics.get_system_health()
