"""
Minimal agent loop.

Uses the provider registry to get the active provider (Ollama offline or
external API). Iterates up to MAX_ITERATIONS, calling tools as requested
by the model, then returning a final answer.

Privacy gate: if privacy mode is active when /api/ask is called,
the loop is never started — the route handler returns 403 before here.
"""

import json
import logging
from typing import Any

import httpx

from backend.harness.providers import provider_registry
from backend.harness.registry import get_tool, tool_schemas_for_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_ITERATIONS = 6
RETRY_LIMIT = 2

SYSTEM_PROMPT_TEMPLATE = """You are SysPilot, a personal AI memory assistant.
You have access to the user's recent activity log — files they edited, commands they ran, and documents they worked on.

CRITICAL RULE — READ FIRST:
You have NO knowledge of the user's activity except what the tools return. You
MUST call a tool (list_events or search_events) BEFORE giving any answer. You
are strictly FORBIDDEN from naming any file, command, URL, or action that did
not appear in a tool result. Never invent events, file names, timestamps, or
commands. If you have not called a tool yet, your only valid response is a tool
call. If the tools return nothing relevant, say you found no matching activity —
do NOT make something up.

Your job:
1. Search the activity log using the provided tools. For "what was I doing"
   style questions, call list_events first. For topic questions, use
   search_events with SHORT keyword queries (1-2 words like "Rust" or "cargo").
   If the first search returns nothing, try a broader single keyword.
2. Answer the user's question based only on what you find.
3. If you infer something not directly stated in the evidence, say "I think..." or "Based on the evidence, it seems...".
4. Never claim the user did something if you have no event that confirms it.
5. Cite the specific events that support your answer (file names, commands, timestamps).
6. When the search returns events, USE them — summarise what they show. Do not
   say "no events found" if the tool returned results.
7. NEVER use the words "mastered", "fully mastered", "fully understood",
   "completed", or "finished" about the user's learning. Activity events only
   show what files were touched or commands run — they say NOTHING about the
   user's level of understanding or mastery. If asked whether they mastered or
   finished something, you MUST begin your answer with a clear hedge such as
   "I can't confirm mastery from the activity log" and then describe only what
   the events show. Example: for "Did I master ownership?" answer "I can't
   confirm whether you mastered it — the log only shows you edited Rust_Notes
   with an ownership section and ran cargo a few times."

Available tools:
{tool_list}

Respond with either a tool call (JSON) or a final answer (plain text).
For tool calls, respond ONLY with valid JSON in this format:
{{"tool": "<tool_name>", "input": {{...}}}}
"""


def _build_system_prompt() -> str:
    tools = tool_schemas_for_model()
    tool_list = "\n".join(
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in tools
    )
    return SYSTEM_PROMPT_TEMPLATE.format(tool_list=tool_list)


def _native_tool_schemas() -> list[dict]:
    """Tool schemas in OpenAI function-calling format."""
    return tool_schemas_for_model()


async def _call_model(messages: list[dict]) -> dict:
    """
    Call the active provider using NATIVE tool-calling and return a structured
    result:

        {"kind": "tool_call", "tool": str, "input": dict}   OR
        {"kind": "text", "text": str}

    Native tool-calling (the provider's `tools` param + structured
    `tool_calls` in the response) is far more reliable than asking the model
    to hand-write JSON in prose, which gpt-oss models do inconsistently.
    """
    provider = provider_registry.get_active_provider()
    response = await provider.generate(
        messages=messages,
        tools=_native_tool_schemas(),
        max_tokens=2048,
    )

    # Extract the assistant message (Ollama: message; OpenAI/Groq: choices[0]).
    msg: dict = {}
    if "message" in response and isinstance(response["message"], dict):
        msg = response["message"]
    elif "choices" in response and response["choices"]:
        msg = response["choices"][0].get("message", {})

    # 1. Native tool_calls (preferred).
    tool_calls = msg.get("tool_calls")
    if tool_calls:
        call = tool_calls[0]
        fn = call.get("function", {})
        name = fn.get("name", "")
        raw_args = fn.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except (json.JSONDecodeError, TypeError):
            args = {}
        if name:
            return {"kind": "tool_call", "tool": name, "input": args, "call_id": call.get("id")}

    # 2. Content text.
    content = (msg.get("content") or "").strip()
    # 3. Fallback: some models emit a text-JSON tool call even with native tools.
    if content:
        parsed = _try_parse_tool_call(content)
        if parsed:
            return {"kind": "tool_call", "tool": parsed["tool"], "input": parsed.get("input", {}), "call_id": None}
        return {"kind": "text", "text": content}

    # 4. Reasoning-only output (gpt-oss) — treat as text but strip it so the
    # loop doesn't surface "I'll search..." prose as an answer.
    reasoning = (msg.get("reasoning") or "").strip()
    return {"kind": "text", "text": reasoning}


def _try_parse_tool_call(text: str) -> dict | None:
    """
    Attempt to parse a tool call JSON from the model output.

    Handles three shapes:
      1. The whole text is a JSON object: {"tool": ..., "input": ...}
      2. The text is wrapped in a ```json ... ``` markdown fence.
      3. Reasoning models (gpt-oss) emit prose followed by the JSON object,
         e.g.  'Let me search... {"tool": "search_events", "input": {...}}'.
         We scan for the LAST balanced {...} block containing a "tool" key.
    Returns the parsed dict if a valid tool call is found, else None.
    """
    text = text.strip()

    # Strip a markdown code fence if present.
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    # Fast path: the whole thing is JSON.
    candidate = text
    if not candidate.startswith("{"):
        # Find an embedded object by scanning for '{"tool"' or '{ "tool"'.
        idx = text.rfind('{"tool"')
        if idx == -1:
            idx = text.rfind("{'tool'")
        if idx == -1:
            # Also try the first '{' that leads to a balanced object with "tool".
            idx = text.find("{")
        if idx == -1:
            return None
        candidate = text[idx:]

    # Trim to a balanced {...} span so trailing prose doesn't break json.loads.
    depth = 0
    end = -1
    for i, ch in enumerate(candidate):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end != -1:
        candidate = candidate[:end]

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None

    if isinstance(parsed, dict) and "tool" in parsed and "input" in parsed:
        return parsed
    return None


def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return its result as a JSON string."""
    tool = get_tool(tool_name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool: {tool_name!r}"})
    try:
        result = tool.execute(tool_input)
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.warning("Tool %r raised: %s", tool_name, exc)
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_agent_loop(
    user_question: str,
    context_hint: str | None = None,
) -> dict[str, Any]:
    """
    Run the agent loop for a single user question.

    Returns:
        {
            "answer": str,          # Final answer text
            "evidence": list[dict], # Events cited as evidence
            "iterations": int,      # Number of model calls made
            "tool_calls": list,     # Log of tools called and their results
        }

    Raises:
        RuntimeError if the loop exceeds MAX_ITERATIONS without a final answer.
    """
    system_prompt = _build_system_prompt()

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    if context_hint:
        messages.append({
            "role": "system",
            "content": f"Context hint from user: {context_hint}",
        })

    messages.append({"role": "user", "content": user_question})

    tool_call_log: list[dict] = []
    cited_event_ids: set[str] = set()
    searched_at_least_once = False
    forced_search_injected = False

    for iteration in range(MAX_ITERATIONS):
        logger.debug("Agent iteration %d", iteration + 1)

        # Retry logic for model timeouts
        result = None
        for attempt in range(RETRY_LIMIT):
            try:
                result = await _call_model(messages)
                break
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.warning(
                    "Model call attempt %d failed: %s", attempt + 1, exc
                )
                if attempt == RETRY_LIMIT - 1:
                    raise RuntimeError(
                        "Model unreachable after retries."
                    ) from exc

        if result["kind"] == "text":
            model_text = result["text"]

            # GUARD: the model must search before it is allowed to answer.
            if not searched_at_least_once and not forced_search_injected:
                forced_search_injected = True
                logger.warning(
                    "Model answered without searching — forcing a search."
                )
                messages.append({
                    "role": "user",
                    "content": (
                        "You have not searched yet. Call the list_events tool "
                        "now (for recent/general activity) or search_events "
                        "with a short keyword (for a topic). Use the tool — do "
                        "not describe what you will do."
                    ),
                })
                continue

            # Searched but no evidence → honest no-data answer.
            if searched_at_least_once and not cited_event_ids:
                return {
                    "answer": (
                        "I couldn't find any matching activity in your log for "
                        "that. I only report what was actually recorded, so "
                        "there's nothing to show here."
                    ),
                    "evidence": [],
                    "iterations": iteration + 1,
                    "tool_calls": tool_call_log,
                }

            # Final answer backed by at least one real event.
            return {
                "answer": model_text,
                "evidence": _collect_evidence(cited_event_ids),
                "iterations": iteration + 1,
                "tool_calls": tool_call_log,
            }

        # --- Tool call ---
        tool_name = result["tool"]
        tool_input = result.get("input", {})
        call_id = result.get("call_id")
        tool_result_str = _execute_tool(tool_name, tool_input)

        if tool_name in ("search_events", "list_events", "get_event"):
            searched_at_least_once = True

        try:
            result_data = json.loads(tool_result_str)
            for ev in result_data.get("events", []):
                if "id" in ev:
                    cited_event_ids.add(ev["id"])
            if "event" in result_data and "id" in result_data["event"]:
                cited_event_ids.add(result_data["event"]["id"])
        except (json.JSONDecodeError, TypeError):
            pass

        tool_call_log.append({
            "tool": tool_name,
            "input": tool_input,
            "result_preview": tool_result_str[:500],
        })

        # Record the assistant tool-call turn and the tool result using the
        # native tool-calling message shape so the provider keeps context.
        if call_id:
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_input),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_result_str,
            })
        else:
            # Fallback (text-JSON path): use plain messages.
            messages.append({
                "role": "assistant",
                "content": json.dumps({"tool": tool_name, "input": tool_input}),
            })
            messages.append({
                "role": "user",
                "content": f"Tool result for {tool_name}:\n{tool_result_str}",
            })

    raise RuntimeError(
        f"Agent loop exceeded MAX_ITERATIONS ({MAX_ITERATIONS}) without a final answer."
    )


def _collect_evidence(event_ids: set[str]) -> list[dict]:
    """Fetch full event records for all cited event IDs."""
    from backend.memory.search import get_event
    evidence = []
    for eid in event_ids:
        ev = get_event(eid)
        if ev:
            evidence.append(ev.model_dump(mode="json"))
    return evidence
