"""
Approval-gated action layer.

The agent never runs a command directly. Instead:
  1. propose_action(command) classifies it and, if allowed, STAGES it,
     returning a one-time pending_id plus the risk and an explanation.
  2. confirm_and_apply(pending_id) runs it ONLY if the id matches an
     outstanding proposal. Proposals are single-use and time-limited.

A classifier bins every command into:
  - read_only        : safe diagnostics, auto-approvable
  - approval_required: changes state; must be confirmed by the user
  - deny             : destructive/forbidden; never staged or run
"""

from __future__ import annotations

import re
import secrets
import shlex
import subprocess
import time

READ_ONLY = "read_only"
APPROVAL_REQUIRED = "approval_required"
DENY = "deny"

# Hard deny — never run these, even with confirmation. Matched as substrings.
_DENY_PATTERNS = [
    r"\brm\s+-rf\s+/\s*$", r"\brm\s+-rf\s+/\s", r":\(\)\s*\{", r"\bmkfs\b",
    r"\bdd\b.*\bof=/dev/", r"\b>\s*/dev/sd", r"\bchmod\s+-R\s+777\s+/",
    r"\bshutdown\b", r"\breboot\b", r"\bhalt\b", r"\bpoweroff\b",
    r"forkbomb", r"\buserdel\b", r"\bpasswd\b", r"\bfdisk\b",
    r"\b>\s*/etc/", r"\bcurl\b.*\|\s*(sudo\s+)?(bash|sh)\b",
    r"\bwget\b.*\|\s*(sudo\s+)?(bash|sh)\b",
]

# Read-only command leaders — safe to run without confirmation.
_READ_ONLY_LEADERS = {
    "df", "du", "free", "ps", "top", "systemctl", "journalctl", "lspci",
    "lsusb", "uname", "uptime", "sensors", "nmcli", "ip", "cat", "ls",
    "systemd-analyze", "dmesg", "whoami", "id", "env", "echo",
}
# systemctl/nmcli are only read-only for their query subcommands.
_READ_ONLY_SUBCOMMANDS = {
    "systemctl": {"status", "list-units", "list-unit-files", "--failed", "show", "is-active", "is-enabled", "cat"},
    "nmcli": {"device", "connection", "general", "radio"},
    "ip": {"addr", "a", "link", "route", "r"},
    "journalctl": set(),  # journalctl is read-only regardless of args
    "dmesg": set(),
}


def classify_command(command: str) -> str:
    """Classify a shell command into read_only / approval_required / deny."""
    cmd = command.strip()
    if not cmd:
        return DENY

    low = cmd.lower()
    for pat in _DENY_PATTERNS:
        if re.search(pat, low):
            return DENY

    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return DENY  # unparseable / unbalanced quotes
    if not tokens:
        return DENY

    # Strip a leading sudo for leader analysis, but sudo implies state change
    # unless the underlying command is purely read-only.
    has_sudo = tokens[0] == "sudo"
    rest = tokens[1:] if has_sudo else tokens
    if not rest:
        return DENY
    leader = rest[0]

    # Pipes/redirects/chaining to a writable target → needs approval.
    if any(sym in cmd for sym in ("&&", "||", ";", ">", ">>")):
        # A pure read pipe (e.g. `journalctl | grep`) is still read-only.
        if leader in _READ_ONLY_LEADERS and "|" in cmd and ">" not in cmd:
            pass
        else:
            return APPROVAL_REQUIRED

    if leader in _READ_ONLY_LEADERS:
        subs = _READ_ONLY_SUBCOMMANDS.get(leader)
        if subs is None:
            return READ_ONLY
        if not subs:  # whole command is read-only (journalctl, dmesg)
            return READ_ONLY
        # Needs a recognised read-only subcommand.
        sub = rest[1] if len(rest) > 1 else ""
        return READ_ONLY if sub in subs else APPROVAL_REQUIRED

    return APPROVAL_REQUIRED


# ---------------------------------------------------------------------------
# Staged proposals
# ---------------------------------------------------------------------------

_PROPOSAL_TTL = 300.0  # seconds a proposal stays valid
_pending: dict[str, dict] = {}


def propose_action(command: str, explanation: str = "") -> dict:
    """
    Classify and (if not denied) stage a command for confirmation.
    Returns {classification, pending_id?, risk, message}.
    Denied commands are never staged.
    """
    classification = classify_command(command)
    if classification == DENY:
        return {
            "classification": DENY,
            "pending_id": None,
            "message": "This command is blocked for safety and cannot be run.",
            "command": command,
        }

    pending_id = secrets.token_hex(8)
    _pending[pending_id] = {
        "command": command,
        "classification": classification,
        "created": time.monotonic(),
    }
    return {
        "classification": classification,
        "pending_id": pending_id,
        "command": command,
        "explanation": explanation,
        "message": (
            "Read-only command staged — safe to apply."
            if classification == READ_ONLY
            else "This command changes your system. Review it, then confirm to run."
        ),
    }


def confirm_and_apply(pending_id: str) -> dict:
    """
    Run a previously proposed command, only if pending_id matches an
    outstanding, non-expired proposal. Single-use.
    """
    entry = _pending.pop(pending_id, None)
    if entry is None:
        return {"status": "error", "message": "No matching pending action (expired or already used)."}

    if time.monotonic() - entry["created"] > _PROPOSAL_TTL:
        return {"status": "error", "message": "This proposal expired. Request it again."}

    # Re-classify at execution time (defence against tampering).
    if classify_command(entry["command"]) == DENY:
        return {"status": "error", "message": "Command is blocked for safety."}

    try:
        result = subprocess.run(
            entry["command"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
        return {
            "status": "ok",
            "command": entry["command"],
            "exit_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Command timed out after 30s."}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": f"Execution failed: {type(exc).__name__}"}


def clear_pending() -> None:
    """Testing helper — drop all staged proposals."""
    _pending.clear()
