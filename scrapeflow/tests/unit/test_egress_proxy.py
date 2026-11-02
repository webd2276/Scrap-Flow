from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from apps.worker.egress_proxy import EgressProxy, ProxyConfig
from packages.core.ssrf import SSRFPolicy


async def _origin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await reader.readuntil(b"\r\n\r\n")
        body = b"hello from origin"
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.fixture
async def origin() -> AsyncIterator[int]:
    server = await asyncio.start_server(_origin, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


def _policy(port: int, *, allow_loopback: bool) -> SSRFPolicy:
    return SSRFPolicy(
        allowed_ports=frozenset({80, port}),
        allowed_private_hosts=frozenset({"127.0.0.1"}) if allow_loopback else frozenset(),
    )


@pytest.fixture
async def proxy(origin: int) -> AsyncIterator[EgressProxy]:
    instance = EgressProxy(ProxyConfig(policy=_policy(origin, allow_loopback=True)))
    await instance.start()
    try:
        yield instance
    finally:
        await instance.stop()


async def test_http_absolute_form_is_forwarded(proxy: EgressProxy, origin: int) -> None:
    async with httpx.AsyncClient(proxy=proxy.url, trust_env=False, timeout=5) as client:
        response = await client.get(f"http://127.0.0.1:{origin}/path?q=1")
    assert response.status_code == 200
    assert response.text == "hello from origin"


async def test_connect_tunnel(proxy: EgressProxy, origin: int) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    try:
        writer.write(
            f"CONNECT 127.0.0.1:{origin} HTTP/1.1\r\nHost: 127.0.0.1:{origin}\r\n\r\n".encode()
        )
        await writer.drain()
        status = await reader.readline()
        assert b"200" in status
        while (await reader.readline()) not in {b"\r\n", b"\n"}:
            pass
        request = f"GET /tunnel HTTP/1.1\r\nHost: 127.0.0.1:{origin}\r\nConnection: close\r\n\r\n"
        writer.write(request.encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), timeout=5)
        assert b"200 OK" in response
        assert b"hello from origin" in response
    finally:
        writer.close()
        await writer.wait_closed()


async def test_private_destination_is_blocked(origin: int) -> None:
    instance = EgressProxy(ProxyConfig(policy=_policy(origin, allow_loopback=False)))
    await instance.start()
    try:
        async with httpx.AsyncClient(proxy=instance.url, trust_env=False, timeout=5) as client:
            response = await client.get(f"http://127.0.0.1:{origin}/")
        assert response.status_code == 403
        assert response.headers["x-scrapeflow-proxy-error"] == "1"
        assert "not public" in response.text
    finally:
        await instance.stop()


async def test_non_http_absolute_target_is_rejected(proxy: EgressProxy) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    try:
        writer.write(b"GET file:///etc/passwd HTTP/1.1\r\nHost: x\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), timeout=5)
        assert b"403" in response
        assert b"http and https" in response
    finally:
        writer.close()
        await writer.wait_closed()


async def test_oversized_headers_are_rejected(proxy: EgressProxy, origin: int) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    try:
        writer.write(
            f"GET http://127.0.0.1:{origin}/ HTTP/1.1\r\nHost: 127.0.0.1\r\n".encode()
            + b"X-Filler: "
            + b"a" * 40_000
            + b"\r\n\r\n"
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), timeout=5)
        assert b"431" in response
    finally:
        writer.close()
        await writer.wait_closed()


async def test_connect_requires_a_port(proxy: EgressProxy) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    try:
        writer.write(b"CONNECT example.com HTTP/1.1\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), timeout=5)
        assert b"400" in response
    finally:
        writer.close()
        await writer.wait_closed()
