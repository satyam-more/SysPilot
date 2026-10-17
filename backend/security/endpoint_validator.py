"""
URL validator for provider endpoints — SSRF prevention.

Validates that a URL is safe to use as a provider API endpoint.
Blocks HTTP, private IP ranges, local hostnames, and credentials in URL.
Never resolves DNS — operates on the literal hostname/IP only.

Custom endpoints are not supported in the first release. The only URL
that passes both validate_provider_url() and _assert_approved_host() is
the hardcoded _TRUSTED_BASE_URL constant in api_provider.py.
"""

import ipaddress
import urllib.parse
from typing import Final

# RFC-1918 and special-purpose ranges that must never be contacted.
_BLOCKED_NETWORKS: Final = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]


class UntrustedEndpointError(Exception):
    """Raised when a URL fails SSRF validation."""
    pass


def validate_provider_url(url: str) -> str:
    """
    Validate that `url` is safe to use as a provider endpoint.
    Returns the validated URL unchanged, or raises UntrustedEndpointError.
    Never resolves DNS — operates on the literal hostname/IP only.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        raise UntrustedEndpointError("Unparseable URL") from exc

    # 1. Scheme must be HTTPS only.
    if parsed.scheme != "https":
        raise UntrustedEndpointError("Only HTTPS provider endpoints are permitted")

    # 2. Must have a hostname.
    hostname = parsed.hostname
    if not hostname:
        raise UntrustedEndpointError("URL has no hostname")

    # 3. Reject bare IP addresses that fall in blocked ranges.
    try:
        addr = ipaddress.ip_address(hostname)
        for blocked in _BLOCKED_NETWORKS:
            if addr in blocked:
                raise UntrustedEndpointError(
                    "Provider endpoint resolves to a private or loopback address"
                )
    except ValueError:
        pass  # hostname is a domain name, not a raw IP — continue

    # 4. Reject hostnames that look like local aliases.
    lower = hostname.lower()
    if lower in ("localhost", "local") or lower.endswith(".local") or lower.endswith(".internal"):
        raise UntrustedEndpointError("Provider endpoint must not target a local hostname")

    # 5. Reject URLs with userinfo (credentials in URL).
    if parsed.username or parsed.password:
        raise UntrustedEndpointError("Credentials must not appear in the provider URL")

    return url
