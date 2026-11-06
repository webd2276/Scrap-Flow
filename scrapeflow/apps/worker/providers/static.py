"""Static proxy-list provider."""

from __future__ import annotations

from packages.core.proxies import ProxyCatalog

from apps.worker.providers.base import CatalogProxyProvider


class StaticProxyProvider(CatalogProxyProvider):
    """Serve a fixed, operator-supplied list of upstream proxies."""

    name = "static"

    def __init__(self, catalog: ProxyCatalog) -> None:
        if catalog.provider != "static":
            raise ValueError("StaticProxyProvider requires a static catalog")
        super().__init__(catalog)
