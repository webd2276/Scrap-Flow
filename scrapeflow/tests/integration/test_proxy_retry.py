from __future__ import annotations

import asyncio
import json
import socket
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

from apps.api.schemas.scrape import ScrapeRequest
from apps.worker import job_store
from apps.worker.scrape import execute_scrape
from packages.core.models import Job, JobKind, JobStatus
from packages.core.proxies import parse_static_proxies
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy
from pydantic import SecretStr

PAGE = b"""<!doctype html>
<html><head><title>Proxy Retry Page</title></head>
<body><h1 id="title">Reached through a proxy</h1></body></html>"""


async def _origin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
            b"Content-Length: " + str(len(PAGE)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + PAGE
        )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


@asynccontextmanager
async def _server(handler: Any) -> AsyncIterator[int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


async def _forwarding_upstream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    origin_port: int,
    authorizations: list[str | None],
    targets: list[str],
) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        _method, target, _version = lines[0].split(" ", 2)
        headers = {
            name.strip().lower(): value.strip()
            for name, _, value in (line.partition(":") for line in lines[1:] if line)
        }
        authorizations.append(headers.get("proxy-authorization"))
        targets.append(target)
        parts = urlsplit(target)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        upstream_reader, upstream_writer = await asyncio.open_connection("127.0.0.1", origin_port)
        upstream_writer.write(
            (
                f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{origin_port}\r\nConnection: close\r\n\r\n"
            ).encode()
        )
        await upstream_writer.drain()
        data = await upstream_reader.read()
        upstream_writer.close()
        writer.write(data)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


def test_scrape_retries_on_the_next_proxy_and_records_only_its_id(
    integration_settings: Settings,
) -> None:
    async def run() -> tuple[Any, list[str | None], list[str], Settings, int]:
        authorizations: list[str | None] = []
        targets: list[str] = []
        async with _server(_origin) as origin_port:
            handler = lambda reader, writer: _forwarding_upstream(  # noqa: E731
                reader,
                writer,
                origin_port=origin_port,
                authorizations=authorizations,
                targets=targets,
            )
            async with _server(handler) as upstream_port:
                dead_port = _closed_port()
                settings = integration_settings.model_copy(
                    update={
                        "proxy_enabled": True,
                        "proxy_static_list": SecretStr(
                            f"DE|http://user:super-secret@127.0.0.1:{dead_port},"
                            f"DE|http://user:super-secret@127.0.0.1:{upstream_port}"
                        ),
                        "proxy_health_check_enabled": False,
                        "proxy_max_retries": 2,
                        "egress_allowed_ports": f"80,443,{origin_port}",
                        "http_timeout_seconds": 10,
                    }
                )
                policy = SSRFPolicy(
                    allowed_ports=frozenset({80, 443, origin_port}),
                    allowed_private_hosts=frozenset({"127.0.0.1"}),
                )
                request = ScrapeRequest(
                    url=f"http://127.0.0.1:{origin_port}/",
                    selectors={"heading": {"css": "h1#title"}},
                    proxy_country="DE",
                )
                job = Job(
                    id=uuid.uuid4(),
                    org_id=uuid.uuid4(),
                    kind=JobKind.SCRAPE,
                    status=JobStatus.RUNNING,
                    url=request.url,
                    payload=request.model_dump(mode="json"),
                    attempts=1,
                    max_attempts=2,
                )
                try:
                    outcome = await execute_scrape(
                        job=job,
                        settings=settings,
                        sessionmaker=job_store.sessionmaker(settings),
                        deadline=time.monotonic() + 30,
                        policy=policy,
                    )
                finally:
                    await job_store.dispose()
                return outcome, authorizations, targets, settings, origin_port

    outcome, authorizations, targets, settings, origin_port = asyncio.run(run())

    assert outcome.result["title"] == "Proxy Retry Page"
    assert outcome.result["selectors"]["heading"] == "Reached through a proxy"
    assert targets == [f"http://127.0.0.1:{origin_port}/"]
    assert authorizations[0] is not None
    assert authorizations[0].startswith("Basic ")
    assert settings.proxy_static_list is not None
    expected = parse_static_proxies(settings.proxy_static_list.get_secret_value())
    assert outcome.result["proxy"] == {
        "id": expected[1].id,
        "provider": "static",
        "country": "DE",
    }
    serialized = json.dumps(outcome.result)
    assert "super-secret" not in serialized
    assert "user:" not in serialized
