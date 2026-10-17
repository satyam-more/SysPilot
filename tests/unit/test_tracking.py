"""
Tests for the activity-tracking config and filesystem collector logic.
"""

import pytest

from backend.database.db import init_db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    import backend.database.db as db_mod
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_mod, "_DB_PATH", db_path)
    monkeypatch.setattr(db_mod, "_DB_DIR", tmp_path)
    monkeypatch.setattr(db_mod, "_conn", None)
    init_db()
    yield
    if db_mod._conn:
        db_mod._conn.close()
    db_mod._conn = None


class TestTrackingConfig:
    def test_watched_directories_empty_by_default(self):
        from backend.collectors import tracking_config
        assert tracking_config.list_watched_directories() == []

    def test_add_and_list_directory(self):
        from backend.collectors import tracking_config
        tracking_config.add_watched_directory("/tmp/foo")
        assert "/tmp/foo" in tracking_config.list_watched_directories()

    def test_add_is_idempotent(self):
        from backend.collectors import tracking_config
        tracking_config.add_watched_directory("/tmp/foo")
        tracking_config.add_watched_directory("/tmp/foo")
        assert tracking_config.list_watched_directories().count("/tmp/foo") == 1

    def test_remove_directory(self):
        from backend.collectors import tracking_config
        tracking_config.add_watched_directory("/tmp/foo")
        tracking_config.remove_watched_directory("/tmp/foo")
        assert "/tmp/foo" not in tracking_config.list_watched_directories()

    def test_default_excluded_folders_present(self):
        from backend.collectors import tracking_config
        folders = tracking_config.get_excluded_folders()
        assert ".git" in folders
        assert "node_modules" in folders

    def test_default_excluded_extensions_present(self):
        from backend.collectors import tracking_config
        exts = tracking_config.get_excluded_extensions()
        assert ".pyc" in exts
        assert ".log" in exts

    def test_set_excluded_folders_persists(self):
        from backend.collectors import tracking_config
        tracking_config.set_excluded_folders(["custom_dir"])
        assert tracking_config.get_excluded_folders() == ["custom_dir"]


class TestFilesystemHandlerExclusions:
    def test_excluded_extension_is_skipped(self, tmp_path):
        from backend.collectors.filesystem import _Handler
        h = _Handler()
        f = tmp_path / "debug.log"
        f.write_text("x")
        assert h._should_skip(str(f)) is True

    def test_excluded_folder_is_skipped(self, tmp_path):
        from backend.collectors.filesystem import _Handler
        h = _Handler()
        nm = tmp_path / "node_modules"
        nm.mkdir()
        f = nm / "index.js"
        f.write_text("x")
        assert h._should_skip(str(f)) is True

    def test_normal_file_not_skipped(self, tmp_path):
        from backend.collectors.filesystem import _Handler
        h = _Handler()
        f = tmp_path / "notes.txt"
        f.write_text("x")
        assert h._should_skip(str(f)) is False

    def test_debounce_blocks_rapid_repeats(self, tmp_path):
        from backend.collectors.filesystem import _Handler
        h = _Handler()
        path = str(tmp_path / "notes.txt")
        # First call records the timestamp and is NOT debounced.
        assert h._debounced(path) is False
        # Immediate second call IS debounced.
        assert h._debounced(path) is True
