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
    question: str = Field(default="", max_length=1000)


@router.post("/ask")
async def ask(
    body: AskRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    history = [{"role": t.role, "content": t.content} for t in body.history]
    return await sysagent.run_system_agent(body.question, history=history)


@router.post("/confirm")
async def confirm(
    body: ConfirmRequest,
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    # Try a staged file write first; if not a file-write id, run as a command.
    result = actions.confirm_file_write(body.pending_id)
    if result.get("status") == "error" and "No matching pending file write" in result.get("message", ""):
        result = actions.confirm_and_apply(body.pending_id)
    # After running, interpret the output into a plain-language insight so the
    # user doesn't have to read raw command output.
    if result.get("status") == "ok":
        insight = await sysagent.interpret_command_result(
            command=result.get("command", ""),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            exit_code=result.get("exit_code", 0),
            question=body.question,
        )
        result["insight"] = insight
    return result


@router.get("/health")
def health(
    request: Request,
    _auth: None = Depends(validate_browser_request),
) -> dict:
    return diagnostics.get_system_health()
