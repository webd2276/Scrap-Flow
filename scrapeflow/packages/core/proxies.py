"""Proxy provider catalog and safe helpers.

Proxy configuration is operator-supplied and may contain credentials, so this
module deliberately exposes only redacted values for logging and results. A
provider returns concrete upstream proxies; the worker's validating egress
proxy still resolves and checks every destination before forwarding traffic.

Supported providers:

* ``static``: a fixed list of ``[COUNTRY|]http(s)://[user:pass@]host:port``.
* ``gateway``: one authenticated rotating gateway URL, optionally with a
  ``{country}`` placeholder in the URL.

No CAPTCHA solving, browser fingerprint spoofing, or stealth features are
implemented here or by any provider.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from packages.core.settings import Settings

_COUNTRY = re.compile(r"^[A-Z]{2}$")
_MAX_PROXY_URL_LENGTH = 2048
_PROXY_FAILURE_MARKERS = (
    "err_proxy_connection_failed",
    "err_tunnel_connection_failed",
    "err_proxy_auth",
    "proxy connection failed",
    "upstream proxy",
)


class ProxyConfigError(ValueError):
    """Raised for malformed proxy configuration; messages never echo URLs."""


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    """One concrete upstream proxy.

    ``url`` is excluded from ``repr`` because it may contain credentials.
    """

    id: str
    provider: str
    country: str | None
    url: str = field(repr=False)

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""

    @property
    def port(self) -> int:
        parts = urlsplit(self.url)
        if parts.port is not None:
            return parts.port
        return 443 if parts.scheme == "https" else 80

    @property
    def safe_url(self) -> str:
        """Return the endpoint without userinfo; safe for logs and results."""
        return redact_proxy_url(self.url)


@dataclass(frozen=True, slots=True)
class ProxyCatalog:
    """A provider's available endpoints and the countries it can serve."""

    provider: str
    endpoints: tuple[ProxyEndpoint, ...]
    countries: frozenset[str]

    def candidates(self, country: str | None) -> tuple[ProxyEndpoint, ...]:
        """Return endpoints eligible for a request.

        An explicit country only matches endpoints configured for it. Without a
        country, generic endpoints win; static providers that only declare
        country-specific entries fall back to the whole list.
        """
        if country is not None:
            if country not in self.countries:
                return ()
            return tuple(endpoint for endpoint in self.endpoints if endpoint.country == country)
        generic = tuple(endpoint for endpoint in self.endpoints if endpoint.country is None)
        return generic or self.endpoints


def _endpoint_id(provider: str, country: str | None, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{provider}-{country.lower() if country else 'any'}-{digest}"


def validate_proxy_url(url: str) -> None:
    if not url or len(url) > _MAX_PROXY_URL_LENGTH:
        raise ProxyConfigError("Proxy URL is empty or too long")
    if any(char.isspace() or ord(char) < 0x20 for char in url):
        raise ProxyConfigError("Proxy URL contains whitespace or control characters")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ProxyConfigError("Proxy URL is malformed") from exc
    if parts.scheme not in {"http", "https"}:
        raise ProxyConfigError("Proxy URL must use http or https")
    if not parts.hostname:
        raise ProxyConfigError("Proxy URL must include a host")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ProxyConfigError("Proxy URL must not include a path, query, or fragment")
    if port is not None and not 1 <= port <= 65535:
        raise ProxyConfigError("Proxy URL has an invalid port")


def redact_proxy_url(url: str) -> str:
    """Strip userinfo from a proxy URL, returning a log-safe value."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return "<invalid-proxy>"
    if not host:
        return "<invalid-proxy>"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
    return f"{parts.scheme}://{host}:{port}"


def parse_static_proxies(raw: str) -> tuple[ProxyEndpoint, ...]:
    """Parse ``[COUNTRY|]url`` entries separated by commas."""
    endpoints: list[ProxyEndpoint] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(raw.split(","), start=1):
        entry = raw_entry.strip()
        if not entry:
            continue
        country: str | None = None
        url = entry
        if "|" in entry:
            prefix, url = entry.split("|", 1)
            country = prefix.strip().upper()
            url = url.strip()
            if not _COUNTRY.fullmatch(country):
                raise ProxyConfigError(f"Invalid country in static proxy entry {index}")
        validate_proxy_url(url)
        endpoint_id = _endpoint_id("static", country, url)
        if endpoint_id in seen:
            continue
        seen.add(endpoint_id)
        endpoints.append(
            ProxyEndpoint(
                id=endpoint_id,
                provider="static",
                country=country,
                url=url,
            )
        )
    if not endpoints:
        raise ProxyConfigError("PROXY_STATIC_LIST must contain at least one proxy")
    return tuple(endpoints)


def build_gateway_catalog(
    gateway_url: str,
    countries: tuple[str, ...],
    default_country: str | None,
) -> ProxyCatalog:
    """Build gateway endpoints, expanding a ``{country}`` placeholder."""
    normalized = tuple(
        sorted({country.strip().upper() for country in countries if country.strip()})
    )
    for country in normalized:
        if not _COUNTRY.fullmatch(country):
            raise ProxyConfigError("PROXY_GATEWAY_COUNTRIES must be comma-separated ISO codes")

    if "{country}" in gateway_url:
        if not normalized:
            raise ProxyConfigError(
                "PROXY_GATEWAY_COUNTRIES is required when the gateway uses {country}"
            )
        if default_country is None:
            raise ProxyConfigError(
                "PROXY_GATEWAY_DEFAULT_COUNTRY is required when the gateway uses {country}"
            )
        if default_country not in normalized:
            raise ProxyConfigError(
                "PROXY_GATEWAY_DEFAULT_COUNTRY must be listed in PROXY_GATEWAY_COUNTRIES"
            )
        endpoints: list[ProxyEndpoint] = []
        for country in normalized:
            url = gateway_url.replace("{country}", country)
            validate_proxy_url(url)
            endpoints.append(
                ProxyEndpoint(
                    id=f"gateway-{country.lower()}",
                    provider="gateway",
                    country=country,
                    url=url,
                )
            )
        default_url = gateway_url.replace("{country}", default_country)
        validate_proxy_url(default_url)
        endpoints.append(
            ProxyEndpoint(
                id="gateway-default",
                provider="gateway",
                country=None,
                url=default_url,
            )
        )
        return ProxyCatalog(
            provider="gateway",
            endpoints=tuple(endpoints),
            countries=frozenset(normalized),
        )

    if "{" in gateway_url or "}" in gateway_url:
        raise ProxyConfigError("PROXY_GATEWAY_URL supports only the {country} placeholder")
    validate_proxy_url(gateway_url)
    return ProxyCatalog(
        provider="gateway",
        endpoints=(
            ProxyEndpoint(
                id="gateway-default",
                provider="gateway",
                country=None,
                url=gateway_url,
            ),
        ),
        countries=frozenset(),
    )


def catalog_from_settings(settings: Settings) -> ProxyCatalog | None:
    """Build the configured provider catalog, or ``None`` when disabled."""
    if not settings.proxy_enabled:
        return None
    if settings.proxy_static_list is not None:
        endpoints = parse_static_proxies(settings.proxy_static_list.get_secret_value())
        countries = frozenset(
            endpoint.country for endpoint in endpoints if endpoint.country is not None
        )
        return ProxyCatalog(provider="static", endpoints=endpoints, countries=countries)
    if settings.proxy_gateway_url is not None:
        return build_gateway_catalog(
            settings.proxy_gateway_url.get_secret_value(),
            settings.proxy_gateway_country_list,
            settings.proxy_gateway_default_country,
        )
    raise ProxyConfigError("PROXY_ENABLED requires a static list or gateway URL")


def looks_like_proxy_failure(error: BaseException) -> bool:
    """Best-effort classification for browser errors caused by the proxy."""
    message = str(error).lower()
    return any(marker in message for marker in _PROXY_FAILURE_MARKERS)


def is_proxy_failure(error: BaseException) -> bool:
    """True when an ``AppError`` was tagged as an upstream proxy failure."""
    details = getattr(error, "details", None)
    return bool(isinstance(details, dict) and details.get("proxy_failure") is True)
