"""Tests for system diagnostics (read-only)."""

from backend.mcp_server import diagnostics as d


def test_system_health_structure():
    h = d.get_system_health()
    assert "cpu" in h and "memory" in h and "disk" in h
    assert h["memory"]["total_mb"] > 0
    assert 0 <= h["memory"]["percent"] <= 100


def test_list_processes_sorted():
    p = d.list_running_processes(limit=5, sort_by="memory")
    assert len(p["processes"]) <= 5
    mems = [x["memory_mb"] for x in p["processes"]]
    assert mems == sorted(mems, reverse=True)


def test_startup_apps_counts():
    s = d.list_startup_apps()
    assert "counts" in s
    assert set(s["counts"]) == {"systemd_system", "systemd_user", "autostart"}


def test_check_issues_structure():
    i = d.check_system_issues()
    assert "issue_count" in i and isinstance(i["issues"], list)
    for issue in i["issues"]:
        assert issue["severity"] in ("high", "medium", "low")
