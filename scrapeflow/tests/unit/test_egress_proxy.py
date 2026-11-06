from __future__ import annotations

import asyncio
import contextlib
import socket
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import httpx
import pytest
from apps.worker.egress_proxy import EgressProxy, ProxyConfig, UpstreamProxy
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


class UpstreamRecorder:
    def __init__(self) -> None:
        self.authorizations: list[str | None] = []
        self.connect_targets: list[str] = []
        self.http_targets: list[str] = []
        self.refuse_connect = False
        self.require_http_auth = False


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                return
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def _upstream_handler(
    recorder: UpstreamRecorder,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        method, target, _version = lines[0].split(" ", 2)
        headers = {
            name.strip().lower(): value.strip()
            for name, _, value in (line.partition(":") for line in lines[1:] if line)
        }
        recorder.authorizations.append(headers.get("proxy-authorization"))
        if method == "CONNECT":
            recorder.connect_targets.append(target)
            if recorder.refuse_connect:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            host, raw_port = target.rsplit(":", 1)
            upstream_reader, upstream_writer = await asyncio.open_connection(host, int(raw_port))
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(
                _pipe(reader, upstream_writer),
                _pipe(upstream_reader, writer),
            )
            return

        recorder.http_targets.append(target)
        if recorder.require_http_auth:
            writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return
        parts = urlsplit(target)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        upstream_reader, upstream_writer = await asyncio.open_connection(
            parts.hostname or "127.0.0.1",
            parts.port or 80,
        )
        upstream_writer.write(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {parts.hostname}:{parts.port}\r\n"
                "Connection: close\r\n\r\n"
            ).encode()
        )
        await upstream_writer.drain()
        data = await upstream_reader.read()
        upstream_writer.close()
        writer.write(data)
        await writer.drain()
    finally:
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()


@pytest.fixture
async def upstream() -> AsyncIterator[tuple[int, UpstreamRecorder]]:
    recorder = UpstreamRecorder()
    server = await asyncio.start_server(
        lambda reader, writer: _upstream_handler(recorder, reader, writer),
        "127.0.0.1",
        0,
    )
    port = int(server.sockets[0].getsockname()[1])
    try:
        yield port, recorder
    finally:
        server.close()
        await server.wait_closed()


def _upstream_proxy(port: int) -> UpstreamProxy:
    return UpstreamProxy.from_url(f"http://user:super-secret@127.0.0.1:{port}")


async def test_connect_tunnel_through_authenticated_upstream(
    origin: int, upstream: tuple[int, UpstreamRecorder]
) -> None:
    upstream_port, recorder = upstream
    instance = EgressProxy(
        ProxyConfig(
            policy=_policy(origin, allow_loopback=True),
            upstream_proxy=_upstream_proxy(upstream_port),
        )
    )
    await instance.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", instance.port)
        try:
            writer.write(
                f"CONNECT 127.0.0.1:{origin} HTTP/1.1\r\nHost: 127.0.0.1:{origin}\r\n\r\n".encode()
            )
            await writer.drain()
            status = await reader.readline()
            assert b"200" in status
            while (await reader.readline()) not in {b"\r\n", b"\n"}:
                pass
            writer.write(b"GET /tunnel HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), timeout=5)
            assert b"hello from origin" in response
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await instance.stop()

    assert recorder.connect_targets == [f"127.0.0.1:{origin}"]
    assert recorder.authorizations[0] is not None
    assert recorder.authorizations[0].startswith("Basic ")
    assert "super-secret" not in repr(_upstream_proxy(upstream_port))


async def test_http_absolute_form_through_upstream(
    origin: int, upstream: tuple[int, UpstreamRecorder]
) -> None:
    upstream_port, recorder = upstream
    instance = EgressProxy(
        ProxyConfig(
            policy=_policy(origin, allow_loopback=True),
            upstream_proxy=_upstream_proxy(upstream_port),
        )
    )
    await instance.start()
    try:
        async with httpx.AsyncClient(proxy=instance.url, trust_env=False, timeout=5) as client:
            response = await client.get(f"http://127.0.0.1:{origin}/path?q=1")
        assert response.status_code == 200
        assert response.text == "hello from origin"
    finally:
        await instance.stop()
    assert recorder.http_targets == [f"http://127.0.0.1:{origin}/path?q=1"]


async def test_upstream_refusal_is_tagged_without_credentials(
    origin: int, upstream: tuple[int, UpstreamRecorder]
) -> None:
    upstream_port, recorder = upstream
    recorder.refuse_connect = True
    instance = EgressProxy(
        ProxyConfig(
            policy=_policy(origin, allow_loopback=True),
            upstream_proxy=_upstream_proxy(upstream_port),
        )
    )
    await instance.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", instance.port)
        try:
            writer.write(
                f"CONNECT 127.0.0.1:{origin} HTTP/1.1\r\nHost: 127.0.0.1:{origin}\r\n\r\n".encode()
            )
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), timeout=5)
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await instance.stop()

    assert b"502" in response
    assert b"X-ScrapeFlow-Proxy-Upstream: 1" in response
    assert b"super-secret" not in response


async def test_unreachable_upstream_is_tagged(origin: int) -> None:
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()
    instance = EgressProxy(
        ProxyConfig(
            policy=_policy(origin, allow_loopback=True),
            upstream_proxy=_upstream_proxy(closed_port),
        )
    )
    await instance.start()
    try:
        async with httpx.AsyncClient(proxy=instance.url, trust_env=False, timeout=5) as client:
            response = await client.get(f"http://127.0.0.1:{origin}/")
        assert response.status_code == 502
        assert response.headers["x-scrapeflow-proxy-upstream"] == "1"
        assert "super-secret" not in response.text
    finally:
        await instance.stop()


async def test_http_upstream_auth_failure_is_tagged(
    origin: int, upstream: tuple[int, UpstreamRecorder]
) -> None:
    upstream_port, recorder = upstream
    recorder.require_http_auth = True
    instance = EgressProxy(
        ProxyConfig(
            policy=_policy(origin, allow_loopback=True),
            upstream_proxy=_upstream_proxy(upstream_port),
        )
    )
    await instance.start()
    try:
        async with httpx.AsyncClient(proxy=instance.url, trust_env=False, timeout=5) as client:
            response = await client.get(f"http://127.0.0.1:{origin}/")
        assert response.status_code == 502
        assert response.headers["x-scrapeflow-proxy-upstream"] == "1"
        assert "super-secret" not in response.text
    finally:
        await instance.stop()
