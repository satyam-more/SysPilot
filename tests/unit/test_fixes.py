"""Tests for the guided-fix generator."""

from backend.mcp_server import fixes as f


def test_known_problems_match():
    for q, word in [
        ("my disk is full", "disk"),
        ("wifi not working", "Wi-Fi"),
        ("boot is slow", "boot"),
        ("a service failed", "service"),
    ]:
        g = f.generate_fix_guide(q)
        assert g["matched"] is True
        assert word.lower() in g["title"].lower()
        assert len(g["steps"]) >= 1


def test_unknown_falls_back_generic():
    g = f.generate_fix_guide("random unknown glitch xyz")
    assert g["matched"] is False
    assert g["steps"]


def test_steps_have_required_fields():
    g = f.generate_fix_guide("disk full")
    for s in g["steps"]:
        assert "step" in s and "explanation" in s
        assert s["risk"] in ("safe", "caution", "high")
