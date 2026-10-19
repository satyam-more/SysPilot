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
4. Be CONCISE. Lead with a one-line direct answer. Keep any explanation to 1-2 short sentences. Do not use headings like "Direct answer / Next step / Explanation". Do not pad.
5. When a tool returns long raw output, SUMMARISE the key facts (2-4 bullet points max) — never paste the full raw dump.
6. When staging a command, show just the command and one short line on why. No long preamble.

Available tools let you read system health, list processes and startup apps, find issues, judge what's safe to close, produce fix guides, and stage commands for approval.

Keep every answer under ~120 words unless the user explicitly asks for detail."""


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


def _api_provider_if_available():
    """
    Return an APIProvider if any API key is configured, else None.
    Preferred for reliable native tool-calling (small local models can't).
    """
    from backend.harness.providers import provider_registry as pr
    from backend.harness.providers.api_provider import APIProvider
    from backend.security.keystore import key_is_configured

    try:
        pr._load_config()
    except Exception:  # noqa: BLE001
        pass

    def _default_model(name: str) -> str:
        return pr.SUPPORTED_PROVIDERS.get(name, {}).get("default_model", "")

    cfg = pr._api_config
    configured = cfg.get("provider")
    if configured and key_is_configured(configured):
        return APIProvider(
            provider=configured,
            model=cfg.get("model") or _default_model(configured),
            key_ref=cfg.get("key_ref") or f"{configured}_key",
        )
    for name in ("groq", "openai"):
        if key_is_configured(name):
            return APIProvider(provider=name, model=_default_model(name), key_ref=f"{name}_key")
    return None


def _local_provider():
    """The offline Ollama provider (best-effort, no tool-calling guarantee)."""
    from backend.harness.providers.ollama_provider import OllamaProvider
    return OllamaProvider()


def _tool_capable_provider():
    """Preferred provider: API if a key exists, else local."""
    return _api_provider_if_available() or _local_provider()


def _parse_response(response: dict) -> dict:
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


async def _call_model(messages: list[dict]) -> dict:
    """
    Call the preferred (API) provider. If it fails due to NO INTERNET, fall
    back to the local Ollama model so the app still works offline (best-effort,
    weaker tool-calling). Returns a parsed result plus which provider answered.
    """
    import httpx

    from backend.harness.providers.api_provider import (
        ModelTimeoutError,
        ProviderUnavailableError,
    )

    api = _api_provider_if_available()
    tools = agent_tools.tool_schemas()

    if api is not None:
        try:
            response = await api.generate(messages=messages, tools=tools, max_tokens=2048)
            return {**_parse_response(response), "_provider": "api"}
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.NetworkError,
            ProviderUnavailableError,
            ModelTimeoutError,
        ):
            logger.warning("API provider unreachable (offline?) — falling back to local model.")
            # fall through to local

    # Local fallback (or no API key configured).
    local = _local_provider()
    response = await local.generate(messages=messages, tools=tools, max_tokens=2048)
    return {**_parse_response(response), "_provider": "local"}


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


async def interpret_command_result(command: str, stdout: str, stderr: str, exit_code: int) -> str:
    """
    After a command runs, produce a short plain-language insight so a
    non-technical user understands the result. No tools — just explanation.
    """
    output = (stdout or "").strip()[:3000]
    err = (stderr or "").strip()[:1000]
    prompt = (
        f"The user approved and ran this command:\n`{command}`\n\n"
        f"Exit code: {exit_code}\n"
        f"Output:\n{output or '(no output)'}\n"
        f"{('Errors:\n' + err) if err else ''}\n\n"
        "Explain the result to a non-technical user in 2-4 short sentences: "
        "what it shows, the key takeaway, and whether anything needs attention. "
        "Use plain language, no raw field dumps. If it looks healthy, say so plainly."
    )
    messages = [
        {"role": "system", "content": "You explain command results in simple, reassuring, plain language."},
        {"role": "user", "content": prompt},
    ]
    provider = _tool_capable_provider()
    try:
        resp = await provider.generate(messages=messages, max_tokens=400)
    except Exception:  # noqa: BLE001
        return ""
    msg: dict = {}
    if "message" in resp and isinstance(resp["message"], dict):
        msg = resp["message"]
    elif "choices" in resp and resp["choices"]:
        msg = resp["choices"][0].get("message", {})
    return (msg.get("content") or msg.get("reasoning") or "").strip()
