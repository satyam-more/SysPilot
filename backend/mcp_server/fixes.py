"""
Guided fix generator.

For a described problem, returns a structured, numbered fix guide: ordered
steps, each with a command (if any), an explanation, and a risk level. This
only EXPLAINS how to fix things — it never executes anything.

A curated knowledge base covers common, high-confidence problems. For anything
not in the KB, a safe generic diagnostic framework is returned so the user
still gets useful, non-destructive guidance.
"""

from __future__ import annotations

# Risk levels per step so the UI/user knows what they're approving.
RISK_SAFE = "safe"        # read-only or trivially reversible
RISK_CAUTION = "caution"  # changes state; reversible with care
RISK_HIGH = "high"        # privileged/destructive; confirm carefully


def _step(n: int, action: str, command: str | None, explain: str, risk: str) -> dict:
    return {"step": n, "action": action, "command": command, "explanation": explain, "risk": risk}


# Curated fix guides. Key = short problem id; matched by keyword below.
_KB: dict[str, dict] = {
    "disk_full": {
        "title": "Free up disk space",
        "keywords": ["disk full", "no space", "storage full", "disk space", "low space"],
        "steps": [
            _step(1, "See what's using space", "df -h /", "Shows how full the root disk is.", RISK_SAFE),
            _step(2, "Find large directories", "du -h --max-depth=1 ~ | sort -rh | head", "Lists your biggest folders so you know where space went.", RISK_SAFE),
            _step(3, "Clear package cache", "sudo apt clean", "Removes downloaded .deb cache. Safe — apt re-downloads if needed.", RISK_CAUTION),
            _step(4, "Remove old journal logs", "sudo journalctl --vacuum-time=7d", "Keeps only the last 7 days of system logs.", RISK_CAUTION),
            _step(5, "Empty the trash", "rm -rf ~/.local/share/Trash/*", "Permanently deletes trashed files. Check the trash first.", RISK_HIGH),
        ],
    },
    "high_memory": {
        "title": "Reduce high memory usage",
        "keywords": ["high memory", "ram full", "out of memory", "memory usage", "slow ram", "swapping"],
        "steps": [
            _step(1, "See top memory users", "ps aux --sort=-%mem | head", "Lists the processes using the most RAM.", RISK_SAFE),
            _step(2, "Close heavy apps you don't need", None, "Browsers with many tabs are common culprits — close unused tabs/apps and save work first.", RISK_SAFE),
            _step(3, "Check swap pressure", "free -h", "If swap is heavily used the system will feel slow.", RISK_SAFE),
            _step(4, "Restart a specific runaway app", None, "Quit and reopen the app identified in step 1 rather than killing it forcefully.", RISK_CAUTION),
        ],
    },
    "failed_service": {
        "title": "Investigate a failed system service",
        "keywords": ["failed service", "service failed", "systemd failed", "unit failed", "service not starting"],
        "steps": [
            _step(1, "List failed units", "systemctl --failed", "Shows which services failed.", RISK_SAFE),
            _step(2, "Read a service's logs", "journalctl -u <service-name> -b --no-pager", "Shows why that service failed this boot. Replace <service-name>.", RISK_SAFE),
            _step(3, "Try restarting it", "sudo systemctl restart <service-name>", "Attempts to bring the service back up.", RISK_CAUTION),
            _step(4, "Check status after restart", "systemctl status <service-name>", "Confirms whether it recovered.", RISK_SAFE),
        ],
    },
    "wifi": {
        "title": "Fix Wi-Fi / network issues",
        "keywords": ["wifi", "wi-fi", "no internet", "network down", "cant connect", "can't connect", "no network"],
        "steps": [
            _step(1, "Check network service", "systemctl status NetworkManager", "Confirms the network manager is running.", RISK_SAFE),
            _step(2, "List devices", "nmcli device", "Shows your network adapters and their state.", RISK_SAFE),
            _step(3, "Restart networking", "sudo systemctl restart NetworkManager", "Restarts networking — reconnects Wi-Fi.", RISK_CAUTION),
            _step(4, "Re-scan networks", "nmcli device wifi rescan && nmcli device wifi list", "Scans for and lists available Wi-Fi networks.", RISK_SAFE),
        ],
    },
    "driver": {
        "title": "Diagnose a driver / hardware issue",
        "keywords": ["driver", "gpu not", "graphics", "no display", "hardware error", "kernel error"],
        "steps": [
            _step(1, "Check kernel messages", "sudo dmesg --level=err,warn | tail -30", "Shows recent hardware/driver errors from the kernel.", RISK_SAFE),
            _step(2, "List hardware & drivers in use", "lspci -k | grep -EA3 'VGA|3D|Network'", "Shows which kernel driver each device is using.", RISK_SAFE),
            _step(3, "Check for missing firmware", "sudo journalctl -b | grep -i firmware", "Missing firmware often causes driver failures.", RISK_SAFE),
            _step(4, "Reinstall the driver package", None, "Identify the driver from steps 1-2, then reinstall it via your package manager. Note the exact package before changing anything.", RISK_HIGH),
        ],
    },
    "slow_boot": {
        "title": "Speed up a slow boot",
        "keywords": ["slow boot", "slow startup", "boot slow", "takes long to start", "startup slow"],
        "steps": [
            _step(1, "See what slows boot", "systemd-analyze blame | head", "Lists services by how long they take at boot.", RISK_SAFE),
            _step(2, "See the critical chain", "systemd-analyze critical-chain", "Shows the boot bottleneck path.", RISK_SAFE),
            _step(3, "Disable an unneeded startup service", "sudo systemctl disable <service-name>", "Stops a non-essential service from starting at boot. Verify it's non-essential first.", RISK_HIGH),
        ],
    },
}


def _match_kb(problem: str) -> dict | None:
    p = problem.lower()
    p_words = set(p.replace("-", " ").split())
    best = None
    best_score = 0.0
    for entry in _KB.values():
        score = 0.0
        for kw in entry["keywords"]:
            if kw in p:
                score += 2.0  # full phrase present
            else:
                # Partial: fraction of the keyword's words present in the input.
                kw_words = kw.split()
                overlap = sum(1 for w in kw_words if w in p_words)
                if overlap:
                    score += overlap / len(kw_words)
        if score > best_score:
            best, best_score = entry, score
    # Require a reasonable match so unrelated text falls back to generic.
    return best if best_score >= 1.0 else None


def generate_fix_guide(problem: str) -> dict:
    """
    Return a numbered fix guide for the described problem.
    Matches a curated knowledge base; falls back to a safe generic framework.
    Never executes anything — guidance only.
    """
    matched = _match_kb(problem)
    if matched:
        return {
            "problem": problem,
            "title": matched["title"],
            "matched": True,
            "steps": matched["steps"],
            "note": "These are suggested steps. Review each before running it; nothing runs automatically.",
        }

    # Generic safe framework for unknown problems.
    generic = [
        _step(1, "Reproduce and note the exact symptom", None, "Write down exactly what happens and when — the error text matters.", RISK_SAFE),
        _step(2, "Check recent system errors", "journalctl -p err -b --no-pager | tail -30", "Recent error logs often name the failing component.", RISK_SAFE),
        _step(3, "Check resource health", "free -h && df -h /", "Rules out memory/disk exhaustion as the cause.", RISK_SAFE),
        _step(4, "Search the exact error", None, "Search the exact error text online for your distro — don't run commands you don't understand.", RISK_SAFE),
    ]
    return {
        "problem": problem,
        "title": "General troubleshooting steps",
        "matched": False,
        "steps": generic,
        "note": "No exact match found, so here is a safe diagnostic starting point.",
    }
