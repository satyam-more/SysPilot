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
def get_battery() -> dict:
    """
    Get battery status and health: charge percent, charging state, and battery
    health (current full capacity vs original design capacity, as a percent).
    Read-only. Use this for any battery question — do not stage a command.
    """
    return diagnostics.get_battery()


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


@mcp.tool()
def get_connectivity() -> dict:
    """
    Check whether Bluetooth and Wi-Fi are turned on or off (via rfkill).
    Read-only. Use for "is my bluetooth on", "is wifi on" questions — do not
    stage a command.
    """
    return diagnostics.get_connectivity()


@mcp.tool()
def get_gpu() -> dict:
    """
    Get the computer's graphics card(s) and the driver in use. Read-only.
    Use for "check my gpu / graphics card" questions — do not stage a command.
    """
    return diagnostics.get_gpu()


@mcp.tool()
def get_network() -> dict:
    """Network status: whether online, active connections, and local IP. Read-only."""
    return diagnostics.get_network()


@mcp.tool()
def get_cpu_info() -> dict:
    """CPU model, core counts, and current usage. Read-only."""
    return diagnostics.get_cpu_info()


@mcp.tool()
def get_memory_details() -> dict:
    """Detailed RAM/swap usage and the top memory-consuming apps. Read-only."""
    return diagnostics.get_memory_details()


@mcp.tool()
def get_temperatures_detail() -> dict:
    """All temperature sensors with a hot/warm/normal verdict. Read-only."""
    return diagnostics.get_temperatures_detail()


@mcp.tool()
def get_uptime() -> dict:
    """How long the computer has been running since last boot. Read-only."""
    return diagnostics.get_uptime()


@mcp.tool()
def get_logged_in_users() -> dict:
    """Currently logged-in users and their sessions. Read-only."""
    return diagnostics.get_logged_in_users()


@mcp.tool()
def get_large_files(path: str = "~", limit: int = 10) -> dict:
    """Largest files under a folder (default home) to help free disk space. Read-only."""
    return diagnostics.get_large_files(path, max(1, min(limit, 30)))


@mcp.tool()
def get_peripherals() -> dict:
    """Connected peripherals: USB devices, keyboard/mouse, and monitors. Read-only."""
    return diagnostics.get_peripherals()


@mcp.tool()
def get_os_info() -> dict:
    """Operating system name, version, kernel, desktop, architecture, hostname. Read-only."""
    return diagnostics.get_os_info()


@mcp.tool()
def get_disk_io() -> dict:
    """Disk read/write activity totals since boot. Read-only."""
    return diagnostics.get_disk_io()


@mcp.tool()
def get_network_traffic() -> dict:
    """Total network data sent/received since boot. Read-only."""
    return diagnostics.get_network_traffic()


@mcp.tool()
def get_top_cpu_processes(limit: int = 10) -> dict:
    """Processes using the most CPU right now. Read-only."""
    return diagnostics.get_top_cpu_processes(max(1, min(limit, 30)))


@mcp.tool()
def get_package_updates() -> dict:
    """How many software/package updates are available. Read-only."""
    return diagnostics.get_package_updates()


@mcp.tool()
def get_kernel_errors() -> dict:
    """Recent kernel errors/warnings (hardware/driver issues). Read-only."""
    return diagnostics.get_kernel_errors()


@mcp.tool()
def get_fan_speed() -> dict:
    """Fan speeds, if sensors report them. Read-only."""
    return diagnostics.get_fan_speed()


@mcp.tool()
def get_mounted_drives() -> dict:
    """All mounted drives/partitions with usage. Read-only."""
    return diagnostics.get_mounted_drives()


@mcp.tool()
def get_swap_info() -> dict:
    """Swap/virtual-memory usage and whether swapping heavily. Read-only."""
    return diagnostics.get_swap_info()


@mcp.tool()
def get_process_by_name(name: str) -> dict:
    """Find running processes matching a name (e.g. is Chrome running). Read-only."""
    return diagnostics.get_process_by_name(name)


@mcp.tool()
def get_gpu_usage() -> dict:
    """Overall GPU load %. Per-app GPU usage isn't available on Linux. Read-only."""
    return diagnostics.get_gpu_usage()


@mcp.tool()
def get_bios_info() -> dict:
    """Motherboard/BIOS vendor, version, date, and laptop model. Read-only."""
    return diagnostics.get_bios_info()


@mcp.tool()
def get_power_info() -> dict:
    """Whether on AC power and current power draw in watts. Read-only."""
    return diagnostics.get_power_info()


@mcp.tool()
def get_cpu_frequency() -> dict:
    """Current, min, and max CPU clock speeds. Read-only."""
    return diagnostics.get_cpu_frequency()


@mcp.tool()
def get_open_ports() -> dict:
    """Network ports the computer is listening on. Read-only."""
    return diagnostics.get_open_ports()


@mcp.tool()
def get_zombie_processes() -> dict:
    """Count of zombie/stuck processes. Read-only."""
    return diagnostics.get_zombie_processes()


@mcp.tool()
def get_disk_health() -> dict:
    """Physical drives and a note on checking SMART health. Read-only."""
    return diagnostics.get_disk_health()


@mcp.tool()
def get_boot_time_analysis() -> dict:
    """Total boot time and slowest startup services. Read-only."""
    return diagnostics.get_boot_time_analysis()


@mcp.tool()
def get_recent_installs() -> dict:
    """Recently installed or upgraded software packages. Read-only."""
    return diagnostics.get_recent_installs()


@mcp.tool()
def get_app_count() -> dict:
    """How many processes/apps are currently running. Read-only."""
    return diagnostics.get_app_count()
