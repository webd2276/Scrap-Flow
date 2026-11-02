from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from apps.worker.egress_proxy import EgressProxy, ProxyConfig
from apps.worker.http_fetch import FetchResult, fetch_url
from packages.core.errors import AppError, ErrorCode
from packages.core.ssrf import SSRFPolicy

PORT: dict[str, int] = {}


async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        target = head.split(b" ")[1]
        port = PORT["port"]
        if target == b"/redirect-private":
            status = b"302 Found"
            headers = f"Location: http://127.0.0.1:{port}/private\r\n".encode()
            body = b""
        elif target == b"/redirect":
            status = b"302 Found"
            headers = b"Location: /final\r\n"
            body = b""
        elif target == b"/slow":
            await asyncio.sleep(2)
            status = b"200 OK"
            headers = b"Content-Type: text/html\r\n"
            body = b"<title>slow</title>"
        elif target == b"/large":
            status = b"200 OK"
            headers = b"Content-Type: text/html\r\n"
            body = b"x" * 200
        else:
            status = b"200 OK"
            headers = b"Content-Type: text/html; charset=utf-8\r\n"
            body = b"<html><title>Fetched</title><body>ok</body></html>"
        writer.write(
            b"HTTP/1.1 "
            + status
            + b"\r\n"
            + headers
            + b"Content-Length: "
            + str(len(body)).encode()
            + b"\r\n"
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def _resolver(host: str, port: int) -> list[str]:
    return ["127.0.0.1"]


@pytest.fixture
async def proxy() -> AsyncIterator[str]:
    server = await asyncio.start_server(_handler, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    PORT["port"] = port
    policy = SSRFPolicy(
        allowed_ports=frozenset({80, port}),
        allowed_private_hosts=frozenset({"public.test"}),
    )
    instance = EgressProxy(ProxyConfig(policy=policy, resolver=_resolver))
    await instance.start()
    try:
        yield instance.url
    finally:
        await instance.stop()
        server.close()
        await server.wait_closed()


def _policy() -> SSRFPolicy:
    return SSRFPolicy(
        allowed_ports=frozenset({80, PORT["port"]}),
        allowed_private_hosts=frozenset({"public.test"}),
    )


async def _fetch(proxy_url: str, path: str, **overrides: object) -> FetchResult:
    options: dict[str, object] = {
        "policy": _policy(),
        "proxy_url": proxy_url,
        "timeout_seconds": 5.0,
        "max_bytes": 10_000,
        "max_redirects": 5,
        "user_agent": "test-agent",
        "resolver": _resolver,
    }
    options.update(overrides)
    return await fetch_url(
        f"http://public.test:{PORT['port']}{path}",
        **options,  # type: ignore[arg-type]
    )


async def test_fetch_returns_body_through_proxy(proxy: str) -> None:
    result = await _fetch(proxy, "/")
    assert result.status_code == 200  # type: ignore[attr-defined]
    assert b"Fetched" in result.content
    assert result.url.startswith("http://public.test:")


async def test_relative_redirect_is_followed(proxy: str) -> None:
    result = await _fetch(proxy, "/redirect")
    assert result.status_code == 200  # type: ignore[attr-defined]
    assert b"Fetched" in result.content
    assert result.redirects


async def test_redirect_to_private_address_is_rejected(proxy: str) -> None:
    with pytest.raises(AppError) as exc:
        await _fetch(proxy, "/redirect-private")
    assert exc.value.code == ErrorCode.BLOCKED_URL


async def test_response_size_limit(proxy: str) -> None:
    with pytest.raises(AppError) as exc:
        await _fetch(proxy, "/large", max_bytes=20)
    assert exc.value.code == ErrorCode.UPSTREAM_ERROR


async def test_upstream_timeout(proxy: str) -> None:
    with pytest.raises(AppError) as exc:
        await _fetch(proxy, "/slow", timeout_seconds=0.2)
    assert exc.value.code == ErrorCode.TIMEOUT


async def test_redirect_limit(proxy: str) -> None:
    with pytest.raises(AppError) as exc:
        await _fetch(proxy, "/redirect", max_redirects=0)
    assert exc.value.code == ErrorCode.UPSTREAM_ERROR
