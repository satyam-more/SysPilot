"""
Tests for the privacy controller.
"""

import threading

import pytest

from backend.privacy.controller import PrivacyController, privacy_controller
from backend.database.db import init_db, get_connection
from backend.memory.events import ingest_event
from backend.memory.models import EventCreate


@pytest.fixture(autouse=True)
def reset_controller():
    """Reset the singleton before each test."""
    PrivacyController._reset()
    yield
    # Clean up after test
    c = PrivacyController()
    c.deactivate_privacy()
    PrivacyController._reset()


def test_is_recording_permitted_true_by_default():
    c = PrivacyController()
    assert c.is_recording_permitted() is True


def test_is_recording_permitted_false_after_activate():
    c = PrivacyController()
    c.activate_privacy()
    assert c.is_recording_permitted() is False


def test_is_recording_permitted_true_after_deactivate():
    c = PrivacyController()
    c.activate_privacy()
    c.deactivate_privacy()
    assert c.is_recording_permitted() is True


def test_activate_writes_privacy_file(tmp_path, monkeypatch):
    c = PrivacyController()
    privacy_file = tmp_path / "privacy_active"
    monkeypatch.setattr(c, "_privacy_file", privacy_file)
    c.activate_privacy()
    assert privacy_file.exists()


def test_deactivate_removes_privacy_file(tmp_path, monkeypatch):
    c = PrivacyController()
    privacy_file = tmp_path / "privacy_active"
    monkeypatch.setattr(c, "_privacy_file", privacy_file)
    c.activate_privacy()
    assert privacy_file.exists()
    c.deactivate_privacy()
    assert not privacy_file.exists()


def test_registered_collector_stop_called_on_activate():
    c = PrivacyController()
    calls = []
    c.register_collector("test", lambda: calls.append("stop"), lambda: "stopped")
    c.activate_privacy()
    assert calls == ["stop"]


def test_get_status_returns_state():
    c = PrivacyController()
    assert c.get_status()["state"] == "active"
    c.activate_privacy()
    assert c.get_status()["state"] == "paused"


def test_activate_returns_collector_acknowledgment():
    c = PrivacyController()
    c.register_collector("fs", lambda: None, lambda: "stopped")
    result = c.activate_privacy()
    assert result["state"] == "paused"
    assert result["collectors"]["fs"] == "stopped"
