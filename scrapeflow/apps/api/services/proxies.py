"""Proxy availability checks at job acceptance."""

from __future__ import annotations

from packages.core.errors import AppError, ErrorCode
from packages.core.proxies import catalog_from_settings
from packages.core.settings import Settings


def ensure_proxy_country(settings: Settings, country: str | None) -> None:
    """Reject a country the configured provider cannot serve.

    Requests without ``proxy_country`` are allowed when the provider is enabled;
    the worker assigns a default/rotating endpoint. With proxies disabled, an
    explicit country is always a 422 rather than being silently ignored.
    """
    if country is None:
        return
    catalog = catalog_from_settings(settings)
    if catalog is None or country not in catalog.countries:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"Proxy country {country} is not available",
        )
