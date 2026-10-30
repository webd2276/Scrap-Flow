"""SSRF guard: stop users from pointing the browser at internal services."""
import ipaddress
import socket
from urllib.parse import urlparse

from . import config


class UnsafeURL(ValueError):
    pass


def assert_safe_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL("Only http/https URLs are allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeURL("URL has no hostname")
    if config.ALLOW_PRIVATE_NETWORKS:
        return url
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL(f"Cannot resolve host: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURL("Target resolves to a non-public address")
    return url
