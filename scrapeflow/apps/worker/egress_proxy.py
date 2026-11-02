"""Validating egress proxy for HTTP and CONNECT traffic.

Every destination is resolved and checked against :mod:`packages.core.ssrf` at
connection time. The proxy then connects to the pinned address, never to the
hostname, which closes the DNS-rebinding window between validation and use.

The proxy is deliberately small: one request per connection, explicit byte and
header caps, and no request transformation beyond removing hop-by-hop headers.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import re
import signal
import socket
import ssl
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlsplit

import structlog
from packages.core.errors import AppError
from packages.core.ssrf import Resolver, SSRFPolicy, resolve_allowed_ips, validate_url

logger = structlog.get_logger(__name__)

_REQUEST_LINE_LIMIT = 8192
_MAX_HEADERS = 100
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
_CRLF = b"\r\n"


class ProxyError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    policy: SSRFPolicy
    resolver: Resolver | None = None
    connect_timeout: float = 10.0
    idle_timeout: float = 30.0
    max_header_bytes: int = 32_768
    max_request_body_bytes: int = 1_048_576


class EgressProxy:
    def __init__(
        self,
        config: ProxyConfig,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self._config = config
        self._host = host
        self._requested_port = port
        self._server: asyncio.AbstractServer | None = None
        self._port = 0
        self._ssl = ssl.create_default_context()

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def start(self) -> EgressProxy:
        self._server = await asyncio.start_server(
            self._handle_client,
            self._host,
            self._requested_port,
            limit=_REQUEST_LINE_LIMIT,
        )
        sockets: list[socket.socket] = list(self._server.sockets or ())
        if not sockets:  # pragma: no cover - defensive
            raise RuntimeError("Egress proxy did not bind a socket")
        self._port = int(sockets[0].getsockname()[1])
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> EgressProxy:
        return await self.start()

    async def __aexit__(self, *exc_info: object) -> None:
        await self.stop()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line, headers = await self._read_head(reader)
            method, target, version = self._parse_request_line(request_line)
            if version not in {"HTTP/1.0", "HTTP/1.1"}:
                raise ProxyError(400, "Unsupported HTTP version")
            if method == "CONNECT":
                await self._handle_connect(target, reader, writer)
            else:
                await self._handle_http(method, target, headers, reader, writer)
        except ProxyError as exc:
            await self._write_error(writer, exc.status, exc.message)
        except AppError as exc:
            await self._write_error(writer, 403, exc.message)
        except TimeoutError:
            await self._write_error(writer, 408, "Upstream timed out")
        except (ConnectionError, OSError):
            await self._write_error(writer, 502, "Upstream connection failed")
        except Exception:  # pragma: no cover - keep the proxy alive
            await self._write_error(writer, 500, "Proxy error")
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _read_head(self, reader: asyncio.StreamReader) -> tuple[bytes, list[bytes]]:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=self._config.idle_timeout)
        except ValueError as exc:
            raise ProxyError(414, "Request line too long") from exc
        if not line:
            raise ProxyError(400, "Empty request")
        if len(line) > _REQUEST_LINE_LIMIT:
            raise ProxyError(414, "Request line too long")
        if not line.endswith(b"\n"):
            raise ProxyError(400, "Incomplete request line")

        headers: list[bytes] = []
        total = len(line)
        while True:
            try:
                raw = await asyncio.wait_for(reader.readline(), timeout=self._config.idle_timeout)
            except ValueError as exc:
                raise ProxyError(431, "Headers too large") from exc
            if not raw:
                raise ProxyError(400, "Incomplete headers")
            total += len(raw)
            if total > self._config.max_header_bytes:
                raise ProxyError(431, "Headers too large")
            if raw in {_CRLF, b"\n"}:
                break
            if raw[:1] in {b" ", b"\t"}:
                raise ProxyError(400, "Obsolete header folding is not allowed")
            if len(headers) >= _MAX_HEADERS:
                raise ProxyError(431, "Too many headers")
            headers.append(raw)
        return line, headers

    def _parse_request_line(self, line: bytes) -> tuple[str, str, str]:
        try:
            method, target, version = line.decode("latin-1").rstrip("\r\n").split(" ")
        except ValueError as exc:
            raise ProxyError(400, "Malformed request line") from exc
        if not method or not target:
            raise ProxyError(400, "Malformed request line")
        return method.upper(), target, version

    async def _handle_connect(
        self,
        authority: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        host, port = self._split_authority(authority)
        ips = await resolve_allowed_ips(host, port, self._config.policy, self._config.resolver)
        upstream_reader, upstream_writer = await self._connect_pinned(ips, port)
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()
        try:
            await self._relay_bidirectional(
                client_reader, client_writer, upstream_reader, upstream_writer
            )
        finally:
            with contextlib.suppress(Exception):
                upstream_writer.close()
                await upstream_writer.wait_closed()

    async def _handle_http(
        self,
        method: str,
        target: str,
        raw_headers: list[bytes],
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        resolved = await validate_url(target, self._config.policy, self._config.resolver)
        headers = self._parse_headers(raw_headers, resolved.host, resolved.port)
        content_length = self._content_length(headers)
        if content_length > self._config.max_request_body_bytes:
            raise ProxyError(413, "Request body too large")

        upstream_reader, upstream_writer = await self._connect_pinned(
            resolved.ips,
            resolved.port,
            tls_hostname=resolved.host if resolved.scheme == "https" else None,
        )
        try:
            path = urlsplit(resolved.url)
            origin_form = path.path or "/"
            if path.query:
                origin_form = f"{origin_form}?{path.query}"
            request = [f"{method} {origin_form} HTTP/1.1".encode("latin-1")]
            request.extend(headers)
            upstream_writer.write(_CRLF.join(request) + _CRLF + _CRLF)
            await upstream_writer.drain()

            remaining = content_length
            while remaining > 0:
                chunk = await asyncio.wait_for(
                    client_reader.read(min(65536, remaining)),
                    timeout=self._config.idle_timeout,
                )
                if not chunk:
                    raise ProxyError(400, "Request body ended early")
                upstream_writer.write(chunk)
                await upstream_writer.drain()
                remaining -= len(chunk)

            await self._relay_response(upstream_reader, client_writer)
        finally:
            with contextlib.suppress(Exception):
                upstream_writer.close()
                await upstream_writer.wait_closed()

    def _parse_headers(self, raw_headers: list[bytes], host: str, port: int) -> list[bytes]:
        parsed: list[tuple[str, str]] = []
        seen: set[str] = set()
        content_lengths: list[str] = []
        has_transfer_encoding = False
        for raw in raw_headers:
            try:
                name_bytes, value_bytes = raw.split(b":", 1)
            except ValueError as exc:
                raise ProxyError(400, "Malformed header") from exc
            name = name_bytes.decode("latin-1").strip()
            value = value_bytes.decode("latin-1").strip()
            if not _HEADER_NAME.fullmatch(name):
                raise ProxyError(400, "Invalid header name")
            lowered = name.lower()
            if lowered in _HOP_BY_HOP or lowered.startswith("proxy-"):
                continue
            if lowered == "host":
                continue
            if lowered == "content-length":
                if lowered in seen:
                    raise ProxyError(400, "Duplicate Content-Length")
                content_lengths.append(value)
            if lowered == "transfer-encoding":
                has_transfer_encoding = True
            if lowered == "expect":
                continue
            if lowered in seen and lowered not in {"cookie", "accept"}:
                # Reject ambiguity for security-sensitive headers.
                continue
            seen.add(lowered)
            parsed.append((name, value))

        if has_transfer_encoding:
            raise ProxyError(411, "Chunked request bodies are not supported")
        if content_lengths:
            parsed.append(("Content-Length", content_lengths[0]))

        default_port = 80 if port == 80 else 443 if port == 443 else None
        host_header = host if default_port == port else f"{host}:{port}"
        if ":" in host and not host.startswith("["):
            host_header = f"[{host}]" if default_port == port else f"[{host}]:{port}"
        parsed.insert(0, ("Host", host_header))
        parsed.append(("Connection", "close"))
        return [f"{name}: {value}".encode("latin-1") for name, value in parsed]

    def _content_length(self, headers: list[bytes]) -> int:
        for raw in headers:
            name, _, value = raw.partition(b":")
            if name.strip().lower() == b"content-length":
                try:
                    length = int(value.strip())
                except ValueError as exc:
                    raise ProxyError(400, "Invalid Content-Length") from exc
                if length < 0:
                    raise ProxyError(400, "Invalid Content-Length")
                return length
        return 0

    async def _connect_pinned(
        self,
        ips: tuple[str, ...],
        port: int,
        *,
        tls_hostname: str | None = None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        last_error: Exception | None = None
        for raw_ip in ips:
            address = _canonical_ip(raw_ip)
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(
                        address,
                        port,
                        ssl=self._ssl if tls_hostname else None,
                        server_hostname=tls_hostname,
                        limit=65_536,
                    ),
                    timeout=self._config.connect_timeout,
                )
            except (OSError, TimeoutError) as exc:
                last_error = exc
                continue
        raise ProxyError(502, "Upstream connection failed") from last_error

    async def _relay_response(
        self,
        upstream_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        status_line = await asyncio.wait_for(
            upstream_reader.readline(), timeout=self._config.idle_timeout
        )
        if not status_line:
            raise ProxyError(502, "Empty upstream response")
        if not status_line.endswith(b"\n"):
            raise ProxyError(502, "Incomplete upstream response")
        headers: list[bytes] = []
        total = len(status_line)
        while True:
            raw = await asyncio.wait_for(
                upstream_reader.readline(), timeout=self._config.idle_timeout
            )
            if not raw:
                raise ProxyError(502, "Incomplete upstream headers")
            total += len(raw)
            if total > self._config.max_header_bytes:
                raise ProxyError(502, "Upstream headers too large")
            headers.append(raw)
            if raw in {_CRLF, b"\n"}:
                break

        client_writer.write(status_line)
        client_writer.writelines(headers)
        await client_writer.drain()

        if _response_is_chunked(headers):
            await self._relay_chunked(upstream_reader, client_writer)
            return
        content_length = _response_content_length(headers)
        if content_length is not None:
            await self._relay_exact(upstream_reader, client_writer, content_length)
            return
        await self._relay_until_eof(upstream_reader, client_writer)

    async def _relay_exact(
        self,
        upstream_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        length: int,
    ) -> None:
        remaining = length
        while remaining > 0:
            data = await asyncio.wait_for(
                upstream_reader.read(min(65536, remaining)),
                timeout=self._config.idle_timeout,
            )
            if not data:
                raise ProxyError(502, "Upstream response ended early")
            client_writer.write(data)
            await client_writer.drain()
            remaining -= len(data)

    async def _relay_chunked(
        self,
        upstream_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        while True:
            size_line = await asyncio.wait_for(
                upstream_reader.readline(), timeout=self._config.idle_timeout
            )
            if not size_line:
                raise ProxyError(502, "Incomplete chunked response")
            client_writer.write(size_line)
            try:
                size = int(size_line.split(b";", 1)[0].strip(), 16)
            except ValueError as exc:
                raise ProxyError(502, "Invalid chunk size") from exc
            if size == 0:
                while True:
                    trailer = await asyncio.wait_for(
                        upstream_reader.readline(), timeout=self._config.idle_timeout
                    )
                    client_writer.write(trailer)
                    if trailer in {_CRLF, b"\n"}:
                        break
                await client_writer.drain()
                return
            remaining = size + 2
            while remaining > 0:
                data = await asyncio.wait_for(
                    upstream_reader.read(min(65536, remaining)),
                    timeout=self._config.idle_timeout,
                )
                if not data:
                    raise ProxyError(502, "Incomplete chunked response")
                client_writer.write(data)
                remaining -= len(data)
            await client_writer.drain()

    async def _relay_until_eof(
        self,
        upstream_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        while True:
            data = await asyncio.wait_for(
                upstream_reader.read(65536), timeout=self._config.idle_timeout
            )
            if not data:
                return
            client_writer.write(data)
            await client_writer.drain()

    async def _relay_bidirectional(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def pipe(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
            while True:
                data = await source.read(65536)
                if not data:
                    return
                destination.write(data)
                await destination.drain()

        tasks = {
            asyncio.create_task(pipe(client_reader, upstream_writer)),
            asyncio.create_task(pipe(upstream_reader, client_writer)),
        }
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    def _split_authority(self, authority: str) -> tuple[str, int]:
        if "@" in authority:
            raise ProxyError(400, "Userinfo is not allowed in CONNECT")
        try:
            parts = urlsplit(f"//{authority}")
            host = parts.hostname
            port = parts.port
        except ValueError as exc:
            raise ProxyError(400, "Invalid CONNECT authority") from exc
        if not host or port is None:
            raise ProxyError(400, "CONNECT requires host:port")
        if parts.path or parts.query:
            raise ProxyError(400, "Invalid CONNECT authority")
        return host, port

    async def _write_error(self, writer: asyncio.StreamWriter, status: int, message: str) -> None:
        reason = {
            400: "Bad Request",
            403: "Forbidden",
            408: "Request Timeout",
            411: "Length Required",
            413: "Payload Too Large",
            414: "URI Too Long",
            431: "Request Header Fields Too Large",
            500: "Internal Server Error",
            502: "Bad Gateway",
        }.get(status, "Error")
        body = message.encode("utf-8", "replace")
        response = (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "X-ScrapeFlow-Proxy-Error: 1\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1") + body
        with contextlib.suppress(Exception):
            writer.write(response)
            await writer.drain()


def _canonical_ip(raw: str) -> str:
    address = ipaddress.ip_address(raw.split("%", 1)[0])
    return str(address)


def _response_content_length(headers: list[bytes]) -> int | None:
    for raw in headers:
        name, _, value = raw.partition(b":")
        if name.strip().lower() == b"content-length":
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


def _response_is_chunked(headers: list[bytes]) -> bool:
    for raw in headers:
        name, _, value = raw.partition(b":")
        if name.strip().lower() == b"transfer-encoding":
            return b"chunked" in value.lower()
    return False


@contextlib.asynccontextmanager
async def running_proxy(config: ProxyConfig) -> AsyncIterator[str]:
    proxy = EgressProxy(config)
    await proxy.start()
    try:
        yield proxy.url
    finally:
        await proxy.stop()


async def serve_forever(config: ProxyConfig, *, host: str, port: int) -> None:
    """Run the proxy until the process receives a signal."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(signal_name, stop.set)

    proxy = EgressProxy(config, host=host, port=port)
    await proxy.start()
    logger.info("egress_proxy.listening", host=host, port=proxy.port)
    try:
        await stop.wait()
    finally:
        await proxy.stop()
        logger.info("egress_proxy.stopped")


def main() -> None:
    """Container entrypoint: ``python -m apps.worker.egress_proxy``."""
    from packages.core.logging import configure_logging
    from packages.core.settings import get_settings

    settings = get_settings()
    configure_logging(settings)
    config = ProxyConfig(
        policy=SSRFPolicy(allowed_ports=settings.egress_port_set),
        connect_timeout=settings.egress_connect_timeout_seconds,
        idle_timeout=settings.egress_idle_timeout_seconds,
        max_header_bytes=settings.egress_max_header_bytes,
    )
    asyncio.run(
        serve_forever(
            config,
            host=settings.egress_proxy_listen_host,
            port=settings.egress_proxy_listen_port,
        )
    )


if __name__ == "__main__":
    main()
