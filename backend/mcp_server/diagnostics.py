"""
System diagnostics — read-only inspection of the machine's health.

Pure functions that gather real system data via psutil and standard Linux
tools (systemctl, journalctl, sensors). Nothing here modifies the system.
Each returns a JSON-serialisable dict for MCP tools to hand back to the client.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timezone

import psutil

logger = logging.getLogger(__name__)

# Commands that need a short timeout so a hung tool never blocks a tool call.
_CMD_TIMEOUT = 5.0


def _run(cmd: list[str]) -> str:
    """Run a read-only shell command, return stdout (empty on failure)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
            check=False,
        )
        return result.stdout
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("Command %s failed: %s", cmd[0], exc)
        return ""


# ---------------------------------------------------------------------------
# System health
# ---------------------------------------------------------------------------

def get_system_health() -> dict:
    """CPU, memory, disk, swap, uptime, and temperature snapshot."""
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    disk = psutil.disk_usage("/")

    boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = (datetime.now(timezone.utc) - boot).total_seconds()

    health = {
        "cpu": {
            "percent": psutil.cpu_percent(interval=0.5),
            "cores": psutil.cpu_count(logical=True),
            "load_avg": list(psutil.getloadavg()),
        },
        "memory": {
            "total_mb": round(vm.total / 1024 / 1024),
            "used_mb": round(vm.used / 1024 / 1024),
            "available_mb": round(vm.available / 1024 / 1024),
            "percent": vm.percent,
        },
        "swap": {
            "total_mb": round(sm.total / 1024 / 1024),
            "used_mb": round(sm.used / 1024 / 1024),
            "percent": sm.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
            "free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
            "percent": disk.percent,
        },
        "uptime_hours": round(uptime_seconds / 3600, 1),
        "temperatures": _get_temperatures(),
    }
    return health


def _get_temperatures() -> dict:
    """Best-effort CPU/GPU temperatures via psutil, fallback to empty."""
    temps: dict[str, float] = {}
    try:
        readings = psutil.sensors_temperatures()
        for chip, entries in readings.items():
            for e in entries:
                if e.current:
                    label = e.label or chip
                    temps[label] = round(e.current, 1)
    except (AttributeError, OSError):
        pass
    return temps


# ---------------------------------------------------------------------------
# Running processes
# ---------------------------------------------------------------------------

def list_running_processes(limit: int = 15, sort_by: str = "memory") -> dict:
    """
    Top processes by memory or cpu. sort_by: 'memory' | 'cpu'.
    Returns name, pid, cpu%, memory_mb for each.
    """
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            mem_mb = round(info["memory_info"].rss / 1024 / 1024, 1) if info.get("memory_info") else 0.0
            procs.append({
                "pid": info["pid"],
                "name": info.get("name") or "unknown",
                "cpu_percent": info.get("cpu_percent") or 0.0,
                "memory_mb": mem_mb,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "memory_mb" if sort_by == "memory" else "cpu_percent"
    procs.sort(key=lambda x: x[key], reverse=True)
    return {"processes": procs[:limit], "total_count": len(procs), "sorted_by": sort_by}


# ---------------------------------------------------------------------------
# Startup / autostart applications
# ---------------------------------------------------------------------------

def list_startup_apps() -> dict:
    """
    Enabled systemd services (system + user) and desktop autostart entries.
    These are the things that run at boot/login and can slow startup.
    """
    result: dict = {"systemd_system": [], "systemd_user": [], "autostart": []}

    # Enabled system services.
    out = _run(["systemctl", "list-unit-files", "--type=service", "--state=enabled", "--no-legend", "--no-pager"])
    for line in out.splitlines():
        parts = line.split()
        if parts:
            result["systemd_system"].append(parts[0])

    # Enabled user services.
    out = _run(["systemctl", "--user", "list-unit-files", "--type=service", "--state=enabled", "--no-legend", "--no-pager"])
    for line in out.splitlines():
        parts = line.split()
        if parts:
            result["systemd_user"].append(parts[0])

    # Desktop autostart entries (XDG).
    import os
    from pathlib import Path
    autostart_dirs = [
        Path.home() / ".config" / "autostart",
        Path("/etc/xdg/autostart"),
    ]
    for d in autostart_dirs:
        if d.is_dir():
            for f in d.glob("*.desktop"):
                result["autostart"].append(f.name)

    result["counts"] = {
        "systemd_system": len(result["systemd_system"]),
        "systemd_user": len(result["systemd_user"]),
        "autostart": len(result["autostart"]),
    }
    return result


# ---------------------------------------------------------------------------
# System issues
# ---------------------------------------------------------------------------

def check_system_issues() -> dict:
    """
    Detect common problems: failed systemd units, recent high-priority errors
    in the journal, low disk space, and high memory/swap pressure.
    """
    issues: list[dict] = []

    # Failed systemd units.
    out = _run(["systemctl", "--failed", "--no-legend", "--no-pager"])
    failed_units = [line.split()[0] for line in out.splitlines() if line.strip()]
    for unit in failed_units:
        issues.append({
            "severity": "high",
            "category": "service",
            "summary": f"Failed service: {unit}",
            "detail": unit,
        })

    # Recent error-level journal messages (last boot, priority err+).
    if shutil.which("journalctl"):
        out = _run(["journalctl", "-p", "err", "-b", "--no-pager", "-n", "20", "-o", "cat"])
        err_lines = [ln for ln in out.splitlines() if ln.strip()]
        # Summarise, don't flood — report count + a few samples.
        if err_lines:
            issues.append({
                "severity": "medium",
                "category": "log",
                "summary": f"{len(err_lines)} recent error-level log entries this boot",
                "detail": err_lines[:5],
            })

    # Resource pressure.
    vm = psutil.virtual_memory()
    if vm.percent > 90:
        issues.append({
            "severity": "high",
            "category": "memory",
            "summary": f"Memory usage is very high ({vm.percent}%)",
            "detail": "The system may become slow or start swapping heavily.",
        })

    disk = psutil.disk_usage("/")
    if disk.percent > 90:
        issues.append({
            "severity": "high",
            "category": "disk",
            "summary": f"Root disk is almost full ({disk.percent}% used)",
            "detail": f"Only {round(disk.free / 1024 / 1024 / 1024, 1)} GB free.",
        })

    sm = psutil.swap_memory()
    if sm.percent > 80:
        issues.append({
            "severity": "medium",
            "category": "memory",
            "summary": f"Swap usage is high ({sm.percent}%)",
            "detail": "Heavy swapping slows the system; consider closing apps.",
        })

    return {
        "issue_count": len(issues),
        "issues": issues,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Safe-to-close analysis
# ---------------------------------------------------------------------------

# Processes that must never be killed — doing so crashes the session or OS.
_CRITICAL_PROCESSES = {
    "systemd", "init", "kthreadd", "dbus-daemon", "dbus-broker",
    "gnome-shell", "gnome-session-binary", "Xorg", "Xwayland", "wayland",
    "gdm", "gdm-session-worker", "pipewire", "wireplumber", "pulseaudio",
    "NetworkManager", "systemd-logind", "systemd-journald", "polkitd",
    "kwin_wayland", "plasmashell", "mutter", "sddm",
}

# User-facing apps that are generally safe to close (data-loss risk only if
# unsaved work). Anything not critical and not a kernel thread falls here.
_KNOWN_SAFE_APPS = {
    "chrome", "firefox", "code", "kiro", "slack", "discord", "spotify",
    "telegram-desktop", "thunderbird", "libreoffice", "obsidian", "vlc",
}


def analyze_safe_to_close(limit: int = 20) -> dict:
    """
    Classify top running processes by how safe they are to close:
      - 'safe'     : user apps; closing only risks unsaved work
      - 'caution'  : unknown/background; may belong to something you need
      - 'critical' : system/session processes; closing can crash the OS/session
    """
    procs = list_running_processes(limit=limit, sort_by="memory")["processes"]
    classified = []
    for p in procs:
        name = (p["name"] or "").lower()
        if name in _CRITICAL_PROCESSES or name.startswith("systemd"):
            level, reason = "critical", "System/session process — closing may crash your desktop or OS."
        elif name in _KNOWN_SAFE_APPS:
            level, reason = "safe", "User application — safe to close; save your work first."
        elif name.startswith("[") or name in ("kthreadd", "ksoftirqd", "migration"):
            level, reason = "critical", "Kernel thread — cannot and must not be closed."
        else:
            level, reason = "caution", "Background/unknown process — verify what it belongs to before closing."
        classified.append({**p, "safety": level, "reason": reason})

    summary = {
        "safe": sum(1 for c in classified if c["safety"] == "safe"),
        "caution": sum(1 for c in classified if c["safety"] == "caution"),
        "critical": sum(1 for c in classified if c["safety"] == "critical"),
    }
    return {"processes": classified, "summary": summary}
