"""
MCP tool registrations for the System Health Assistant.

Each tool is a plain function decorated with @mcp.tool(). The MCP SDK derives
the input schema from the type hints and the tool description from the
docstring, then exposes them to any MCP client (including Alexa+).

For now this contains a single trivial ping tool to verify the MCP handshake.
Real diagnostic tools are added in later steps.
"""

from backend.mcp_server import diagnostics
from backend.mcp_server.server import mcp


@mcp.tool()
def ping() -> str:
    """
    Health check. Returns 'pong' to confirm the MCP server is reachable and
    tool invocation works. Use this to verify connectivity.
    """
    return "pong"


@mcp.tool()
def get_system_health() -> dict:
    """
    Get a snapshot of the computer's health: CPU usage and load, memory and
    swap usage, root disk space, uptime, and component temperatures.
    Read-only. Use this to answer "how is my system doing / is it healthy".
    """
    return diagnostics.get_system_health()


@mcp.tool()
def list_running_processes(limit: int = 15, sort_by: str = "memory") -> dict:
    """
    List the top running processes. sort_by is 'memory' (default) or 'cpu'.
    Returns each process's name, pid, CPU percent, and memory in MB.
    Read-only. Use this for "what's using my memory/CPU / what's running".
    """
    if sort_by not in ("memory", "cpu"):
        sort_by = "memory"
    limit = max(1, min(limit, 50))
    return diagnostics.list_running_processes(limit=limit, sort_by=sort_by)


@mcp.tool()
def list_startup_apps() -> dict:
    """
    List applications and services that start automatically at boot or login:
    enabled systemd system services, user services, and desktop autostart
    entries. Read-only. Use this for "what starts with my computer / what is
    slowing my boot".
    """
    return diagnostics.list_startup_apps()


@mcp.tool()
def check_system_issues() -> dict:
    """
    Scan for common problems: failed system services, recent error-level log
    entries, low disk space, and high memory/swap pressure. Returns a list of
    issues with severity (high/medium) and a short summary of each.
    Read-only. Use this for "what's wrong with my system / any problems".
    """
    return diagnostics.check_system_issues()


@mcp.tool()
def analyze_safe_to_close(limit: int = 20) -> dict:
    """
    Analyse running processes and classify each as safe, caution, or critical
    to close. 'safe' = user apps (only unsaved-work risk); 'caution' =
    background/unknown; 'critical' = system/session/kernel processes that must
    not be closed. Read-only — does not close anything. Use this for "which
    apps can I safely close".
    """
    limit = max(1, min(limit, 50))
    return diagnostics.analyze_safe_to_close(limit=limit)


@mcp.tool()
def generate_fix_guide(problem: str) -> dict:
    """
    Produce a numbered, step-by-step guide to fix a described system problem
    (e.g. "disk is full", "wifi not working", "boot is slow", "a service
    failed"). Each step includes the command, an explanation, and a risk level
    (safe/caution/high). This ONLY explains how to fix the problem — it never
    runs anything. Use this whenever the user asks how to fix or solve an issue.
    """
    from backend.mcp_server import fixes
    return fixes.generate_fix_guide(problem)


@mcp.tool()
def propose_action(command: str, explanation: str = "") -> dict:
    """
    Stage a system command for the user to review before it runs. Classifies
    the command as read_only, approval_required, or deny. Denied commands are
    blocked and never staged. For allowed commands, returns a one-time
    pending_id the user must confirm. ALWAYS use this before any command that
    changes the system — never assume a command has run.
    """
    from backend.mcp_server import actions
    return actions.propose_action(command, explanation)


@mcp.tool()
def confirm_and_apply(pending_id: str) -> dict:
    """
    Execute a command that was previously staged by propose_action, using its
    pending_id. Only runs if the id matches an outstanding, non-expired
    proposal. This is the explicit human-approval gate — call it only after the
    user has agreed to run the staged command.
    """
    from backend.mcp_server import actions
    return actions.confirm_and_apply(pending_id)
