"""
Tests for the browser-history collector's pure logic:
URL exclusion, domain parsing, and timestamp conversion.
"""

from datetime import datetime, timezone

from backend.collectors.browser_history import (
    _chromium_ts_to_dt,
    _domain,
    _firefox_ts_to_dt,
    _is_excluded,
)


class TestDomainParsing:
    def test_extracts_hostname(self):
        assert _domain("https://www.example.com/path?q=1") == "www.example.com"

    def test_empty_for_garbage(self):
        assert _domain("not a url") == ""


class TestExclusion:
    def test_excluded_exact_domain(self):
        assert _is_excluded("https://mail.google.com/inbox", ["mail.google.com"]) is True

    def test_excluded_subdomain(self):
        assert _is_excluded("https://foo.example.com/x", ["example.com"]) is True

    def test_not_excluded(self):
        assert _is_excluded("https://github.com/x", ["example.com"]) is False

    def test_auth_host_always_excluded(self):
        # accounts.google.* is noise regardless of the user's exclusion list.
        assert _is_excluded("https://accounts.google.com/signin", []) is True
        assert _is_excluded("https://accounts.google.co.in/accounts/SetSID", []) is True

    def test_setsid_path_excluded(self):
        assert _is_excluded("https://example.com/accounts/SetSID?x=1", []) is True

    def test_unparseable_excluded(self):
        assert _is_excluded("", []) is True


class TestTimestampConversion:
    def test_chromium_epoch(self):
        # 13436716936845538 µs since 1601 → a 2026 date.
        dt = _chromium_ts_to_dt(13436716936845538)
        assert dt.tzinfo is not None
        assert dt.year == 2026

    def test_firefox_epoch(self):
        # Firefox: µs since 1970.
        now_us = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        dt = _firefox_ts_to_dt(now_us)
        assert dt.tzinfo is not None
        assert dt.year >= 2025
