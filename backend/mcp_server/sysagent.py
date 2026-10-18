"""
System-health agent loop.

Runs the active model (Groq/Ollama) with native tool-calling against the
system-health tools. The model diagnoses and explains; it never executes
state-changing commands itself — propose_action stages them and the user
confirms via confirm_and_apply (surfaced in the UI as a confirmation gate).
"""

from __future__ import annotations

import json
import logging

import httpx

from backend.harness.providers import provider_registry
from backend.mcp_server import agent_tools

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6
RETRY_LIMIT = 2

SYSTEM_PROMPT = """You are a System Health Assistant. You help the user understand and fix problems on their Linux computer.

CRITICAL RULES:
1. You have NO knowledge of the system except what the tools return. Always call a tool before stating any fact about the machine. Never invent process names, numbers, or services.
2. For "how to fix" questions, call generate_fix_guide and present the numbered steps clearly.
3. You must NEVER claim to have run or changed anything. To change the system, call propose_action to STAGE a command — it returns a pending action the USER must confirm. Never fabricate a result.
4. Be concise and practical. Lead with the direct answer, then supporting detail.

Available tools let you read system health, list processes and startup apps, find issues, judge what's safe to close, produce fix guides, and stage commands for approval."""


_FAKE_TOOL_SIGNS = (
    "tool_read", "tool_", "$system", "please run", "run the command",
    "run the following", "i will use the", "let me check that for you",
    "run this command", "execute the command",
)


def _looks_like_fake_tool_use(text: str) -> bool:
    """
    Heuristic: the model is pretending to use a tool (writing tool-ish text or
    asking the user to run a command) instead of actually calling one.
    """
    low = text.lower()
    return any(sign in low for sign in _FAKE_TOOL_SIGNS)


async def _call_model(messages: list[dict]) -> dict:
    provider = provider_registry.get_active_provider()
    response = await provider.generate(
        messages=messages, tools=agent_tools.tool_schemas(), max_tokens=2048
    )
    msg: dict = {}
    if "message" in response and isinstance(response["message"], dict):
        msg = response["message"]
    elif "choices" in response and response["choices"]:
        msg = response["choices"][0].get("message", {})

    tcs = msg.get("tool_calls")
    if tcs:
        fn = tcs[0].get("function", {})
        raw = fn.get("arguments", "{}")
        try:
            args = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            args = {}
        return {"kind": "tool_call", "tool": fn.get("name", ""), "input": args, "call_id": tcs[0].get("id")}

    content = (msg.get("content") or "").strip()
    if content:
        return {"kind": "text", "text": content}
    return {"kind": "text", "text": (msg.get("reasoning") or "").strip()}


async def run_system_agent(question: str, history: list[dict] | None = None) -> dict:
    """
    Answer a system-health question. Returns:
      {answer, tool_calls: [...], pending_action: {...}|None}
    pending_action is set when the agent staged a command needing confirmation.

    `history` is prior [{role, content}] turns (user/assistant text only) so
    the model keeps conversation context across questions.
    """
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Include recent prior turns (text only) for context. Cap to keep the
    # context small and tokens cheap.
    if history:
        for turn in history[-6:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    tool_log: list[dict] = []
    pending_action: dict | None = None
    forced_tool_nudge = False

    for i in range(MAX_ITERATIONS):
        result = None
        for attempt in range(RETRY_LIMIT):
            try:
                result = await _call_model(messages)
                break
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if attempt == RETRY_LIMIT - 1:
                    raise RuntimeError("Model unreachable after retries.") from exc

        if result["kind"] == "text":
            text = result["text"]

            # Guard: some weak models (small local LLMs) don't emit real tool
            # calls — they write fake tool-ish text ("tool_read_system_health",
            # "please run `free`") without calling anything. If no tool has run
            # yet and the text looks like that, nudge once to force a real call.
            if not tool_log and _looks_like_fake_tool_use(text) and not forced_tool_nudge:
                forced_tool_nudge = True
                messages.append({
                    "role": "user",
                    "content": (
                        "Do not describe commands or ask me to run them. Use "
                        "your available tools directly to get the real data, "
                        "then answer from the tool results."
                    ),
                })
                continue

            return {
                "answer": text,
                "tool_calls": tool_log,
                "pending_action": pending_action,
                "iterations": i + 1,
            }

        name = result["tool"]
        args = result.get("input", {})
        call_id = result.get("call_id")
        out = agent_tools.execute(name, args)

        # If the agent staged a command, surface it as the confirmation gate.
        if name == "propose_action" and isinstance(out, dict) and out.get("pending_id"):
            pending_action = {
                "pending_id": out["pending_id"],
                "command": out.get("command"),
                "classification": out.get("classification"),
                "message": out.get("message"),
            }

        out_str = json.dumps(out, default=str)
        tool_log.append({"tool": name, "input": args, "result_preview": out_str[:400]})

        if call_id:
            messages.append({
                "role": "assistant", "content": None,
                "tool_calls": [{"id": call_id, "type": "function",
                                "function": {"name": name, "arguments": json.dumps(args)}}],
            })
            messages.append({"role": "tool", "tool_call_id": call_id, "content": out_str})
        else:
            messages.append({"role": "assistant", "content": json.dumps({"tool": name, "input": args})})
            messages.append({"role": "user", "content": f"Tool result for {name}:\n{out_str}"})

    return {
        "answer": "I gathered system information but couldn't finish forming an answer. Try asking more specifically.",
        "tool_calls": tool_log,
        "pending_action": pending_action,
        "iterations": MAX_ITERATIONS,
    }
