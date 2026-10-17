"""
External API model provider — OpenAI-compatible.

Uses a hardcoded trusted base URL. No custom endpoints in the first release.
SSRF prevention: validate_provider_url() + _assert_approved_host() called
before every outbound request. follow_redirects=False.
"""

import logging
import urllib.parse

import httpx

from backend.harness.providers.base import ModelProvider, ProviderStatus
from backend.security.endpoint_validator import (
    UntrustedEndpointError,
    validate_provider_url,
)
from backend.security.keystore import KeyNotFoundError, get_key, key_is_configured

logger = logging.getLogger(__name__)

# Trusted provider endpoints. These are hardcoded constants — not read from
# user input or the database. Each is OpenAI-compatible (same /chat/completions
# and /models API shape). Adding a provider here requires a code change + review.
_PROVIDER_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
}

# Validate every endpoint at import time — fails fast if one is malformed.
_VALIDATED_ENDPOINTS: dict[str, str] = {
    name: validate_provider_url(url) for name, url in _PROVIDER_ENDPOINTS.items()
}

# Backwards-compatible default (OpenAI) still exported for existing imports/tests.
_TRUSTED_BASE_URL = _PROVIDER_ENDPOINTS["openai"]
_VALIDATED_BASE_URL = _VALIDATED_ENDPOINTS["openai"]

# Exact allowlist of approved provider hostnames. A URL whose hostname is not
# here is rejected before any request — blocks subdomain spoofing / tampering.
_APPROVED_PROVIDER_HOSTS: frozenset[str] = frozenset(
    urllib.parse.urlparse(url).hostname for url in _PROVIDER_ENDPOINTS.values()
)


def _endpoint_for(provider: str) -> str:
    """Return the validated base URL for a provider, defaulting to OpenAI."""
    return _VALIDATED_ENDPOINTS.get(provider, _VALIDATED_BASE_URL)


class InvalidAPIKeyError(Exception):
    pass


class RateLimitError(Exception):
    def __init__(self, retry_after: str | None = None):
        self.retry_after = retry_after


class ProviderUnavailableError(Exception):
    pass


class ModelTimeoutError(Exception):
    pass


class MalformedResponseError(Exception):
    pass


def _assert_approved_host(url: str) -> None:
    """
    Final guard: confirm the URL's hostname is on the approved list.
    Called before every outbound request.
    """
    hostname = urllib.parse.urlparse(url).hostname
    if hostname not in _APPROVED_PROVIDER_HOSTS:
        raise UntrustedEndpointError("Provider hostname is not on the approved list.")


class APIProvider(ModelProvider):
    def __init__(self, provider: str = "openai", model: str = "gpt-4o-mini", key_ref: str = ""):
        self._provider = provider
        self._model = model
        self._key_ref = key_ref

    async def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> dict:
        base_url = _endpoint_for(self._provider)
        # Assert approved host before any HTTP call.
        _assert_approved_host(base_url)

        # Retrieve key immediately before use — do not cache.
        if not self._key_ref:
            raise InvalidAPIKeyError("No API key configured")
        key = get_key(self._key_ref)
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                follow_redirects=False,
                timeout=httpx.Timeout(30.0),
            ) as client:
                response = await client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=self._build_request(messages, tools, max_tokens),
                )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("Provider request timed out") from exc
        finally:
            del key  # Remove local reference immediately

        return self._parse_response(response)

    def _build_request(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        max_tokens: int,
    ) -> dict:
        req = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            req["tools"] = tools
        return req

    def _parse_response(self, response: httpx.Response) -> dict:
        if response.status_code == 401:
            raise InvalidAPIKeyError("Provider rejected the API key")
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimitError(retry_after=retry_after)
        if response.is_redirect:
            loc = response.headers.get("location", "")
            parsed_loc = urllib.parse.urlparse(loc)
            raise ProviderUnavailableError(
                f"Unexpected redirect from provider to host: {parsed_loc.hostname}"
            )
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            raise MalformedResponseError("Provider returned non-JSON response")

    async def health_check(self) -> ProviderStatus:
        configured = key_is_configured(self._provider)
        if not configured:
            return ProviderStatus(
                mode="api",
                model=self._model,
                connected=False,
                error="No API key configured",
                key_configured=False,
                key_persistent=False,
            )
        from backend.security.keystore import storage_is_persistent

        persistent = storage_is_persistent(self._provider)
        base_url = _endpoint_for(self._provider)
        try:
            _assert_approved_host(base_url)
            key = get_key(self._key_ref or f"{self._provider}_key")
        except KeyNotFoundError:
            return ProviderStatus(
                mode="api",
                model=self._model,
                connected=False,
                error="API key not found in store",
                key_configured=False,
            )

        # Real validation: a lightweight GET /models call confirms the key
        # actually works. No inference, no local compute — just a key check.
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                follow_redirects=False,
                timeout=httpx.Timeout(10.0),
            ) as client:
                resp = await client.get(
                    "/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
        except httpx.TimeoutException:
            return ProviderStatus(
                mode="api", model=self._model, connected=False,
                error="Connection to provider timed out",
                key_configured=True, key_persistent=persistent,
            )
        except httpx.HTTPError:
            return ProviderStatus(
                mode="api", model=self._model, connected=False,
                error="Could not reach provider. Check your network connection.",
                key_configured=True, key_persistent=persistent,
            )
        finally:
            del key

        if resp.status_code == 401:
            return ProviderStatus(
                mode="api", model=self._model, connected=False,
                error="API key was rejected by the provider. Check the key is correct.",
                key_configured=True, key_persistent=persistent,
            )
        if resp.status_code >= 400:
            return ProviderStatus(
                mode="api", model=self._model, connected=False,
                error=f"Provider returned status {resp.status_code}",
                key_configured=True, key_persistent=persistent,
            )

        return ProviderStatus(
            mode="api",
            model=self._model,
            connected=True,
            error=None,
            key_configured=True,
            key_persistent=persistent,
        )

    def get_active_model(self) -> str:
        return self._model
