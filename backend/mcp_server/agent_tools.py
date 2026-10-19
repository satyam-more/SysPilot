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
    "get_gpu": {
        "fn": lambda **k: diagnostics.get_gpu(),
        "description": "Graphics card(s) and driver in use. Use for GPU/graphics questions.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_network": {
        "fn": lambda **k: diagnostics.get_network(),
        "description": "Network status: online, active connections, local IP.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_cpu_info": {
        "fn": lambda **k: diagnostics.get_cpu_info(),
        "description": "CPU model, core counts, and current usage.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_memory_details": {
        "fn": lambda **k: diagnostics.get_memory_details(),
        "description": "Detailed RAM/swap usage and top memory consumers.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_temperatures_detail": {
        "fn": lambda **k: diagnostics.get_temperatures_detail(),
        "description": "All temperature sensors with a hot/warm/normal verdict.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_uptime": {
        "fn": lambda **k: diagnostics.get_uptime(),
        "description": "How long the computer has been running since last boot.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_logged_in_users": {
        "fn": lambda **k: diagnostics.get_logged_in_users(),
        "description": "Currently logged-in users and sessions.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_large_files": {
        "fn": lambda path="~", limit=10, **k: diagnostics.get_large_files(str(path), max(1, min(int(limit), 30))),
        "description": "Largest files under a folder (default home) to help free disk space.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}},
    },
    "get_peripherals": {
        "fn": lambda **k: diagnostics.get_peripherals(),
        "description": "Connected peripherals: USB devices, keyboard/mouse, and monitors. Use for keyboard/mouse/monitor/USB questions.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_os_info": {
        "fn": lambda **k: diagnostics.get_os_info(),
        "description": "Operating system name, version, kernel, desktop, architecture, hostname.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_disk_io": {
        "fn": lambda **k: diagnostics.get_disk_io(),
        "description": "Disk read/write activity totals since boot.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_network_traffic": {
        "fn": lambda **k: diagnostics.get_network_traffic(),
        "description": "Total network data sent/received since boot.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_top_cpu_processes": {
        "fn": lambda limit=10, **k: diagnostics.get_top_cpu_processes(max(1, min(int(limit), 30))),
        "description": "Processes using the most CPU right now.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
    "get_package_updates": {
        "fn": lambda **k: diagnostics.get_package_updates(),
        "description": "How many software/package updates are available.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_kernel_errors": {
        "fn": lambda **k: diagnostics.get_kernel_errors(),
        "description": "Recent kernel errors/warnings (hardware/driver issues).",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_fan_speed": {
        "fn": lambda **k: diagnostics.get_fan_speed(),
        "description": "Fan speeds, if sensors report them.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_mounted_drives": {
        "fn": lambda **k: diagnostics.get_mounted_drives(),
        "description": "All mounted drives/partitions with usage.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_swap_info": {
        "fn": lambda **k: diagnostics.get_swap_info(),
        "description": "Swap/virtual-memory usage and whether swapping heavily.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_process_by_name": {
        "fn": lambda name="", **k: diagnostics.get_process_by_name(str(name)),
        "description": "Find running processes matching a name (e.g. 'chrome', 'is X running').",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    "get_gpu_usage": {
        "fn": lambda **k: diagnostics.get_gpu_usage(),
        "description": "Overall GPU load percentage (per-app GPU usage isn't available on Linux).",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_bios_info": {
        "fn": lambda **k: diagnostics.get_bios_info(),
        "description": "Motherboard/BIOS vendor, version, date, laptop model.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_power_info": {
        "fn": lambda **k: diagnostics.get_power_info(),
        "description": "Whether on AC power and current power draw in watts.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_cpu_frequency": {
        "fn": lambda **k: diagnostics.get_cpu_frequency(),
        "description": "Current, min, and max CPU clock speeds.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_open_ports": {
        "fn": lambda **k: diagnostics.get_open_ports(),
        "description": "Network ports the computer is listening on.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_zombie_processes": {
        "fn": lambda **k: diagnostics.get_zombie_processes(),
        "description": "Count of zombie/stuck processes.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_disk_health": {
        "fn": lambda **k: diagnostics.get_disk_health(),
        "description": "Physical drives and a note on checking SMART health.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_boot_time_analysis": {
        "fn": lambda **k: diagnostics.get_boot_time_analysis(),
        "description": "Total boot time and the slowest services at startup.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_recent_installs": {
        "fn": lambda **k: diagnostics.get_recent_installs(),
        "description": "Recently installed or upgraded software packages.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_app_count": {
        "fn": lambda **k: diagnostics.get_app_count(),
        "description": "How many processes/apps are currently running.",
        "parameters": {"type": "object", "properties": {}},
    },
    "propose_file_write": {
        "fn": lambda path="", content="", mode="create", **k: actions.propose_file_write(str(path), str(content), str(mode)),
        "description": "Create, overwrite, or append to a file in the user's home folder. STAGES the write for user approval (never writes directly). Use when asked to create/edit/save a file or note. mode is 'create', 'overwrite', or 'append'.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (in home folder)"},
                "content": {"type": "string", "description": "File contents"},
                "mode": {"type": "string", "enum": ["create", "overwrite", "append"]},
            },
            "required": ["path", "content"],
        },
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
