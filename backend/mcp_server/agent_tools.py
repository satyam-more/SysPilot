"""
System-agent tool registry.

Wraps the same diagnostic/fix/action functions that the MCP tools expose, in
the OpenAI function-calling schema the agent loop uses. One source of truth:
these call into diagnostics.py / fixes.py / actions.py, exactly like the MCP
tools do — so the web agent and Alexa+ behave identically.
"""

from __future__ import annotations

from typing import Any

from backend.mcp_server import actions, diagnostics, fixes

# name -> (callable, json-schema parameters)
_TOOLS: dict[str, dict[str, Any]] = {
    "get_system_health": {
        "fn": lambda **k: diagnostics.get_system_health(),
        "description": "Get CPU, memory, swap, disk, uptime and temperatures.",
        "parameters": {"type": "object", "properties": {}},
    },
    "list_running_processes": {
        "fn": lambda limit=15, sort_by="memory", **k: diagnostics.list_running_processes(
            limit=max(1, min(int(limit), 50)), sort_by=sort_by if sort_by in ("memory", "cpu") else "memory"
        ),
        "description": "Top running processes by memory or cpu.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many (1-50)"},
                "sort_by": {"type": "string", "enum": ["memory", "cpu"]},
            },
        },
    },
    "list_startup_apps": {
        "fn": lambda **k: diagnostics.list_startup_apps(),
        "description": "Apps/services that start at boot or login.",
        "parameters": {"type": "object", "properties": {}},
    },
    "check_system_issues": {
        "fn": lambda **k: diagnostics.check_system_issues(),
        "description": "Scan for failed services, log errors, resource pressure.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_battery": {
        "fn": lambda **k: diagnostics.get_battery(),
        "description": "Battery charge, charging state, and health (full vs design capacity). Use for any battery question — do not stage a command.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_connectivity": {
        "fn": lambda **k: diagnostics.get_connectivity(),
        "description": "Whether Bluetooth and Wi-Fi are on or off. Use for bluetooth/wifi questions — do not stage a command.",
        "parameters": {"type": "object", "properties": {}},
    },
    "analyze_safe_to_close": {
        "fn": lambda limit=20, **k: diagnostics.analyze_safe_to_close(limit=max(1, min(int(limit), 50))),
        "description": "Classify running processes safe/caution/critical to close.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
    },
    "generate_fix_guide": {
        "fn": lambda problem="", **k: fixes.generate_fix_guide(str(problem)),
        "description": "Numbered step-by-step guide to fix a described problem.",
        "parameters": {
            "type": "object",
            "properties": {"problem": {"type": "string", "description": "The problem to fix"}},
            "required": ["problem"],
        },
    },
    "propose_action": {
        "fn": lambda command="", explanation="", **k: actions.propose_action(str(command), str(explanation)),
        "description": "Stage a command for user approval (classifies read_only/approval_required/deny). Use before any state-changing command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["command"],
        },
    },
}


def tool_schemas() -> list[dict]:
    """OpenAI function-calling tool schemas for the system agent."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for name, spec in _TOOLS.items()
    ]


def execute(name: str, args: dict) -> Any:
    """Run a tool by name with kwargs. Returns a JSON-serialisable result."""
    spec = _TOOLS.get(name)
    if spec is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return spec["fn"](**(args or {}))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
