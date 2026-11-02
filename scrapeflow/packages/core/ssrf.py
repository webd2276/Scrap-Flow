"""SSRF validation shared by the API, worker, HTTP fetcher, and egress proxy.

The validator resolves every hostname and denies any non-global address. DNS is
resolved again at connect time by the egress proxy, which then connects to the
pinned address; this closes the rebinding window between validation and use.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from packages.core.errors import AppError, ErrorCode

Resolver = Callable[[str, int], Awaitable[list[str]]]

DEFAULT_ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
MAX_URL_LENGTH = 2048

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True, slots=True)
class SSRFPolicy:
    allowed_ports: frozenset[int] = field(default=DEFAULT_ALLOWED_PORTS)
    allowed_private_hosts: frozenset[str] = field(default_factory=frozenset)
    max_url_length: int = MAX_URL_LENGTH

    def private_allowed(self, host: str) -> bool:
        return host.strip("[]").lower() in self.allowed_private_hosts


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    url: str
    scheme: str
    host: str
    port: int
    ips: tuple[str, ...]

    @property
    def origin(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}:{self.port}"


async def default_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def _reject(message: str, *, code: ErrorCode = ErrorCode.BLOCKED_URL) -> AppError:
    return AppError(422, code, message)


def _normalise_host(host: str) -> str:
    stripped = host.strip("[]").strip().lower().rstrip(".")
    if not stripped:
        raise _reject("URL has no host", code=ErrorCode.INVALID_URL)
    if len(stripped) > 253:
        raise _reject("Hostname is too long", code=ErrorCode.INVALID_URL)
    try:
        return str(_parse_ip(stripped))
    except ValueError:
        pass
    try:
        return stripped.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise _reject("Hostname is not valid IDNA", code=ErrorCode.INVALID_URL) from exc


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True only for unicast, globally routable addresses.

    ``is_global`` alone is not enough: Python reports multicast space (for
    example 224.0.0.1) as global on some versions. Deny the special-use
    classes explicitly before trusting ``is_global``.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_public(ip.ipv4_mapped)
    if ip.is_unspecified or ip.is_loopback or ip.is_link_local:
        return False
    if ip.is_multicast or ip.is_reserved or ip.is_private:
        return False
    return bool(ip.is_global)


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    return ipaddress.ip_address(value.split("%", 1)[0])


async def resolve_allowed_ips(
    host: str,
    port: int,
    policy: SSRFPolicy,
    resolver: Resolver | None = None,
) -> tuple[str, ...]:
    """Resolve a host and return only addresses allowed by the policy."""
    normalised = _normalise_host(host)
    if port not in policy.allowed_ports:
        raise _reject(f"Port {port} is not allowed")

    if policy.private_allowed(normalised):
        # Test-only escape hatch used with a loopback fixture. Production
        # deployments never populate allowed_private_hosts.
        try:
            ips = await (resolver or default_resolver)(normalised, port)
        except (socket.gaierror, OSError) as exc:
            raise _reject("Hostname did not resolve", code=ErrorCode.DNS_FAILURE) from exc
        return tuple(ips)

    if _looks_like_ip(normalised):
        try:
            literal = _parse_ip(normalised)
        except ValueError as exc:
            raise _reject("Invalid IP address", code=ErrorCode.INVALID_URL) from exc
        if not _is_public(literal):
            raise _reject("Destination address is not public")
        return (str(literal),)

    try:
        raw_ips = await (resolver or default_resolver)(normalised, port)
    except (socket.gaierror, OSError) as exc:
        raise _reject("Hostname did not resolve", code=ErrorCode.DNS_FAILURE) from exc
    if not raw_ips:
        raise _reject("Hostname did not resolve", code=ErrorCode.DNS_FAILURE)

    allowed: list[str] = []
    for raw in raw_ips:
        try:
            ip = _parse_ip(raw)
        except ValueError as exc:
            raise _reject(
                "Resolver returned an invalid address", code=ErrorCode.DNS_FAILURE
            ) from exc
        if not _is_public(ip):
            raise _reject("Destination address is not public")
        allowed.append(str(ip))
    return tuple(sorted(set(allowed)))


def _looks_like_ip(host: str) -> bool:
    try:
        _parse_ip(host)
    except ValueError:
        return False
    return True


async def validate_url(
    raw_url: str,
    policy: SSRFPolicy | None = None,
    resolver: Resolver | None = None,
) -> ResolvedTarget:
    """Validate scheme, authority, port, and every resolved address."""
    policy = policy or SSRFPolicy()
    url = raw_url.strip()
    if not url:
        raise _reject("URL is required", code=ErrorCode.INVALID_URL)
    if len(url) > policy.max_url_length:
        raise _reject(f"URL exceeds {policy.max_url_length} characters", code=ErrorCode.INVALID_URL)
    if _CONTROL_CHARS.search(url) or "\\" in url:
        raise _reject("URL contains forbidden characters", code=ErrorCode.INVALID_URL)

    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise _reject("URL is malformed", code=ErrorCode.INVALID_URL) from exc

    scheme = parts.scheme.lower()
    if scheme not in _SCHEMES:
        raise _reject("Only http and https URLs are supported", code=ErrorCode.INVALID_URL)
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise _reject("URL userinfo is not allowed", code=ErrorCode.INVALID_URL)
    if not parts.hostname:
        raise _reject("URL has no host", code=ErrorCode.INVALID_URL)

    host = _normalise_host(parts.hostname)
    try:
        port = parts.port if parts.port is not None else (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise _reject("URL port is invalid", code=ErrorCode.INVALID_URL) from exc
    if port not in policy.allowed_ports:
        raise _reject(f"Port {port} is not allowed")

    netloc_host = f"[{host}]" if ":" in host else host
    normalised_url = urlunsplit(
        (scheme, f"{netloc_host}:{port}", parts.path or "/", parts.query, "")
    )

    ips = await resolve_allowed_ips(host, port, policy, resolver)
    return ResolvedTarget(
        url=normalised_url,
        scheme=scheme,
        host=host,
        port=port,
        ips=ips,
    )


def validate_redirect(current: ResolvedTarget, location: str, policy: SSRFPolicy) -> str:
    """Resolve a Location header and forbid HTTPS-to-HTTP downgrades."""
    from urllib.parse import urljoin

    target = urljoin(current.url, location)
    try:
        scheme = urlsplit(target).scheme.lower()
    except ValueError as exc:
        raise _reject("Redirect URL is malformed", code=ErrorCode.INVALID_URL) from exc
    if current.scheme == "https" and scheme == "http":
        raise _reject("Redirect would downgrade HTTPS to HTTP")
    return target
