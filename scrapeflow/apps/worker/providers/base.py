"""Proxy provider interface.

Providers only select upstream proxies. Destination validation and connection
pinning remain the egress proxy's job, so a provider can never bypass SSRF
checks by returning a special URL.
"""

from __future__ import annotations

from typing import Protocol

from packages.core.proxies import ProxyCatalog, ProxyEndpoint


class ProxyProvider(Protocol):
    name: str

    def candidates(self, country: str | None) -> tuple[ProxyEndpoint, ...]: ...


class CatalogProxyProvider:
    """Shared implementation over a validated :class:`ProxyCatalog`."""

    name = "catalog"

    def __init__(self, catalog: ProxyCatalog) -> None:
        self.catalog = catalog

    def candidates(self, country: str | None) -> tuple[ProxyEndpoint, ...]:
        return self.catalog.candidates(country)
