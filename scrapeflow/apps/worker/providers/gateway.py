"""Authenticated rotating-gateway proxy provider."""

from __future__ import annotations

from packages.core.proxies import ProxyCatalog

from apps.worker.providers.base import CatalogProxyProvider


class GatewayProxyProvider(CatalogProxyProvider):
    """Serve endpoints derived from a gateway URL template.

    Rotation is performed by the gateway; this provider exposes one endpoint per
    configured country plus a default endpoint for requests without a country.
    """

    name = "gateway"

    def __init__(self, catalog: ProxyCatalog) -> None:
        if catalog.provider != "gateway":
            raise ValueError("GatewayProxyProvider requires a gateway catalog")
        super().__init__(catalog)
