from __future__ import annotations

import socket

import pytest
from packages.core.errors import AppError, ErrorCode
from packages.core.ssrf import (
    ResolvedTarget,
    SSRFPolicy,
    resolve_allowed_ips,
    validate_redirect,
    validate_url,
)

PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"


async def resolver_public(host: str, port: int) -> list[str]:
    return [PUBLIC_V4, PUBLIC_V6]


async def resolver_private(host: str, port: int) -> list[str]:
    return [PUBLIC_V4, "10.0.0.5"]


async def resolver_empty(host: str, port: int) -> list[str]:
    return []


async def resolver_gaierror(host: str, port: int) -> list[str]:
    raise socket.gaierror("no such host")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hi",
        "ftp://example.com/file",
        "//example.com/path",
        "http://",
        "http://user:pass@example.com/",
        "http://user%40host@example.com/",
        "http://example.com\\@127.0.0.1/",
        "http://example.com:22/",
        "http://example.com:0/",
        "http://example.com:65536/",
        "http://exa\x00mple.com/",
        "http://" + "a" * 3000 + ".com/",
    ],
)
async def test_invalid_urls_are_rejected(url: str) -> None:
    with pytest.raises(AppError) as exc:
        await validate_url(url, resolver=resolver_public)
    assert exc.value.status_code == 422
    assert exc.value.code in {ErrorCode.INVALID_URL, ErrorCode.BLOCKED_URL}


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.1.2.3",
        "10.1.2.3",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",  # noqa: S104 - literal test input
        "192.0.2.10",
        "198.51.100.10",
        "203.0.113.10",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
async def test_non_global_literal_addresses_are_blocked(ip: str) -> None:
    host = f"[{ip}]" if ":" in ip else ip
    with pytest.raises(AppError) as exc:
        await validate_url(f"http://{host}/", resolver=resolver_public)
    assert exc.value.code == ErrorCode.BLOCKED_URL


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", PUBLIC_V6])
async def test_global_literal_addresses_are_allowed(ip: str) -> None:
    host = f"[{ip}]" if ":" in ip else ip
    target = await validate_url(f"https://{host}/x", resolver=resolver_public)
    assert target.host == ip
    assert target.port == 443


async def test_resolved_private_address_is_blocked() -> None:
    with pytest.raises(AppError) as exc:
        await validate_url("https://looks-public.example/", resolver=resolver_private)
    assert exc.value.code == ErrorCode.BLOCKED_URL


async def test_mixed_public_private_answer_is_blocked() -> None:
    with pytest.raises(AppError) as exc:
        await resolve_allowed_ips("example.com", 443, SSRFPolicy(), resolver_private)
    assert exc.value.code == ErrorCode.BLOCKED_URL


async def test_empty_and_failed_dns_are_dns_failures() -> None:
    for resolver in (resolver_empty, resolver_gaierror):
        with pytest.raises(AppError) as exc:
            await validate_url("https://example.com/", resolver=resolver)
        assert exc.value.code == ErrorCode.DNS_FAILURE


async def test_private_hosts_require_explicit_test_policy() -> None:
    policy = SSRFPolicy(allowed_private_hosts=frozenset({"127.0.0.1"}))
    target = await validate_url("http://127.0.0.1:8080/health", policy, resolver_public)
    assert target.port == 8080
    assert target.ips == ("93.184.216.34", PUBLIC_V6)


async def test_url_is_canonicalised() -> None:
    target = await validate_url("HTTPS://Example.COM./Path?q=1#frag", resolver=resolver_public)
    assert target.url == "https://example.com:443/Path?q=1"
    assert target.scheme == "https"
    assert target.host == "example.com"


async def test_ipv6_origin_uses_brackets() -> None:
    target = await validate_url(f"http://[{PUBLIC_V6}]/", resolver=resolver_public)
    assert target.origin == f"http://[{PUBLIC_V6}]:80"


def test_https_to_http_redirect_is_rejected() -> None:
    current = ResolvedTarget(
        url="https://example.com:443/", scheme="https", host="example.com", port=443, ips=()
    )
    with pytest.raises(AppError) as exc:
        validate_redirect(current, "http://example.com/next", SSRFPolicy())
    assert exc.value.code == ErrorCode.BLOCKED_URL


def test_relative_redirect_is_resolved() -> None:
    current = ResolvedTarget(
        url="https://example.com:443/a/b", scheme="https", host="example.com", port=443, ips=()
    )
    assert validate_redirect(current, "../c?x=1", SSRFPolicy()) == "https://example.com:443/c?x=1"
