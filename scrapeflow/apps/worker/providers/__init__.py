"""Build the configured proxy provider."""

from __future__ import annotations

from packages.core.proxies import ProxyConfigError, catalog_from_settings
from packages.core.settings import Settings

from apps.worker.providers.base import ProxyProvider
from apps.worker.providers.gateway import GatewayProxyProvider
from apps.worker.providers.static import StaticProxyProvider


def build_provider(settings: Settings) -> ProxyProvider:
    """Return the provider selected by settings.

    Settings validation guarantees exactly one provider is configured when
    ``PROXY_ENABLED`` is true; a missing catalog is still treated as a
    configuration error rather than silently disabling the feature.
    """
    catalog = catalog_from_settings(settings)
    if catalog is None:
        raise ProxyConfigError("Proxy providers are disabled")
    if catalog.provider == "static":
        return StaticProxyProvider(catalog)
    if catalog.provider == "gateway":
        return GatewayProxyProvider(catalog)
    raise ProxyConfigError("Unknown proxy provider")  # pragma: no cover - exhaustive
