"""
Tests for the SSRF endpoint validator.
"""

import pytest

from backend.security.endpoint_validator import UntrustedEndpointError, validate_provider_url

BLOCKED = [
    "http://api.openai.com/v1",           # http not https
    "https://127.0.0.1/v1",               # loopback IP
    "https://localhost/v1",               # local hostname
    "https://192.168.1.1/v1",             # RFC-1918
    "https://10.0.0.1/v1",               # RFC-1918
    "https://172.16.0.1/v1",             # RFC-1918
    "https://169.254.169.254/latest",     # AWS metadata link-local
    "https://user:pass@api.openai.com/",  # credentials in URL
    "ftp://api.openai.com/v1",            # wrong scheme
    "",                                   # empty string
    "not-a-url",                          # no scheme
    "https://[::1]/v1",                   # IPv6 loopback
    "https://host.local/v1",              # .local mDNS
    "https://host.internal/v1",           # .internal
]

ALLOWED = [
    "https://api.openai.com/v1",
    "https://api.anthropic.com",
    "https://generativelanguage.googleapis.com/v1beta",
]


@pytest.mark.parametrize("url", BLOCKED)
def test_blocked_urls_raise(url: str) -> None:
    with pytest.raises(UntrustedEndpointError):
        validate_provider_url(url)


@pytest.mark.parametrize("url", ALLOWED)
def test_allowed_urls_pass(url: str) -> None:
    result = validate_provider_url(url)
    assert result == url


def test_returns_url_unchanged() -> None:
    url = "https://api.openai.com/v1"
    assert validate_provider_url(url) == url


def test_credentials_in_url_blocked() -> None:
    with pytest.raises(UntrustedEndpointError, match="Credentials"):
        validate_provider_url("https://user:secret@api.openai.com/v1")


def test_loopback_ip_blocked() -> None:
    with pytest.raises(UntrustedEndpointError):
        validate_provider_url("https://127.0.0.1/v1")


def test_private_range_blocked() -> None:
    for ip in ["10.0.0.1", "192.168.100.1", "172.31.255.255"]:
        with pytest.raises(UntrustedEndpointError):
            validate_provider_url(f"https://{ip}/v1")
