"""
Minimal agent loop.

Connects to the local Ollama model (offline) or an external API provider.
Iterates up to MAX_ITERATIONS, calling tools as requested by the model,
then returning a final answer.

Privacy gate: if privacy mode is active when /api/ask is called,
the loop is never started — the route handler returns 403 before here.
"""

import json
import logging
from typing import Any

import httpx

from backend.harness.registry import get_tool, tool_schemas_for_model
from backend.memory.search import search_events

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_ITERATIONS = 6
TOOL_TIMEOUT_SECONDS = 10
MODEL_TIMEOUT_SECONDS = 30
RETRY_LIMIT = 2

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"

SYSTEM_PROMPT_TEMPLATE = """You are TrailBack, a personal AI memory assistant.
You have access to the user's recent activity log — files they edited, commands they ran, and documents they worked on.

Your job:
1. Search the activity log using the provided tools.
2. Answer the user's question based only on what you find.
3. If you infer something not directly stated in the evidence, say "I think..." or "Based on the evidence, it seems...".
4. Never claim the user did something if you have no event that confirms it.
5. Cite the specific events that support your answer (file names, commands, timestamps).

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


def _call_ollama(messages: list[dict], timeout: float = MODEL_TIMEOUT_SECONDS) -> str:
    """Send a chat request to Ollama and return the assistant message content."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


def _try_parse_tool_call(text: str) -> dict | None:
    """
    Attempt to parse a tool call JSON from the model output.
    Returns the parsed dict if valid, None if it's a plain text answer.
    """
    text = text.strip()
    # Look for a JSON object starting with {"tool":
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
        if "tool" in parsed and "input" in parsed:
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
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

def run_agent_loop(
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

    for iteration in range(MAX_ITERATIONS):
        logger.debug("Agent iteration %d", iteration + 1)

        # Retry logic for model timeouts
        model_response = None
        for attempt in range(RETRY_LIMIT):
            try:
                model_response = _call_ollama(messages)
                break
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.warning(
                    "Model call attempt %d failed: %s", attempt + 1, exc
                )
                if attempt == RETRY_LIMIT - 1:
                    raise RuntimeError(
                        "Model unreachable after retries."
                    ) from exc

        # Check if the model is making a tool call
        tool_call = _try_parse_tool_call(model_response)

        if tool_call is None:
            # Model gave a final answer — extract any cited event IDs
            return {
                "answer": model_response,
                "evidence": _collect_evidence(cited_event_ids),
                "iterations": iteration + 1,
                "tool_calls": tool_call_log,
            }

        # Execute the tool
        tool_name = tool_call["tool"]
        tool_input = tool_call.get("input", {})
        tool_result_str = _execute_tool(tool_name, tool_input)

        # Track event IDs returned by search/list tools
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

        # Add the exchange to the conversation
        messages.append({"role": "assistant", "content": model_response})
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
