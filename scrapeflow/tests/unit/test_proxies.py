from __future__ import annotations

from pathlib import Path

import pytest
from packages.core.proxies import (
    ProxyConfigError,
    build_gateway_catalog,
    catalog_from_settings,
    is_proxy_failure,
    looks_like_proxy_failure,
    parse_static_proxies,
    redact_proxy_url,
)
from packages.core.settings import Settings
from pydantic import ValidationError


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "api_key_pepper": "a" * 40,
        "jwt_secret": "b" * 40,
        "webhook_secret_key": "c" * 40,
        "artifacts_local_dir": str(tmp_path),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_static_proxies_parse_country_and_redact_credentials(tmp_path: Path) -> None:
    raw = "DE|http://user:super-secret@de.proxy:8080, http://global.proxy:3128"
    settings = _settings(tmp_path, proxy_enabled=True, proxy_static_list=raw)
    catalog = catalog_from_settings(settings)

    assert catalog is not None
    assert catalog.provider == "static"
    assert catalog.countries == frozenset({"DE"})
    assert len(catalog.endpoints) == 2
    assert {endpoint.country for endpoint in catalog.endpoints} == {None, "DE"}

    german = catalog.candidates("DE")
    assert len(german) == 1
    assert german[0].safe_url == "http://de.proxy:8080"
    assert "super-secret" not in repr(german[0])
    assert "user" not in repr(german[0])
    assert "super-secret" not in redact_proxy_url(german[0].url)
    assert catalog.candidates("US") == ()


def test_static_proxies_without_country_fall_back_to_all_for_default() -> None:
    endpoints = parse_static_proxies("DE|http://a.proxy:1,US|http://b.proxy:2")
    from packages.core.proxies import ProxyCatalog

    static_catalog = ProxyCatalog("static", endpoints, frozenset({"DE", "US"}))
    assert {endpoint.country for endpoint in static_catalog.candidates(None)} == {"DE", "US"}


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://proxy:21",
        "DE|http://proxy:8080/path",
        "DEU|http://proxy:8080",
        "http://proxy:99999",
        "   ",
    ],
)
def test_static_proxy_entries_are_validated_without_echoing_secrets(raw: str) -> None:
    with pytest.raises(ProxyConfigError) as exc:
        parse_static_proxies(raw)
    assert "password" not in str(exc.value)


def test_gateway_country_expansion_and_default(tmp_path: Path) -> None:
    catalog = build_gateway_catalog(
        "http://user-{country}:pass@gateway.example:8080",
        ("DE", "US"),
        "US",
    )
    assert catalog.countries == frozenset({"DE", "US"})
    default = catalog.candidates(None)
    assert len(default) == 1
    assert default[0].id == "gateway-default"
    assert "user-US" in default[0].url
    assert "user-DE" in catalog.candidates("DE")[0].url
    assert catalog.candidates("FR") == ()
    assert "pass" not in repr(catalog.candidates("DE")[0])


def test_gateway_without_country_does_not_claim_country_support() -> None:
    catalog = build_gateway_catalog("http://gateway.example:8080", ("DE",), None)
    assert catalog.countries == frozenset()
    assert catalog.candidates("DE") == ()
    assert catalog.candidates(None)[0].url == "http://gateway.example:8080"


def test_gateway_requires_default_country_with_placeholder() -> None:
    with pytest.raises(ProxyConfigError):
        build_gateway_catalog("http://user-{country}:pass@gateway:8080", ("DE",), None)
    with pytest.raises(ProxyConfigError):
        build_gateway_catalog("http://user-{country}:pass@gateway:8080", (), "DE")
    with pytest.raises(ProxyConfigError):
        build_gateway_catalog("http://user-{session}:pass@gateway:8080", ("DE",), "DE")


def test_settings_require_exactly_one_proxy_provider(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        _settings(tmp_path, proxy_enabled=True)
    with pytest.raises(ValidationError):
        _settings(
            tmp_path,
            proxy_enabled=True,
            proxy_static_list="http://a:1",
            proxy_gateway_url="http://b:2",
        )


def test_settings_validate_gateway_placeholder_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        _settings(
            tmp_path,
            proxy_enabled=True,
            proxy_gateway_url="http://user-{country}:pass@gateway:8080",
        )
    with pytest.raises(ValidationError):
        _settings(
            tmp_path,
            proxy_enabled=True,
            proxy_gateway_url="http://user-{country}:pass@gateway:8080",
            proxy_gateway_countries="DE",
        )
    settings = _settings(
        tmp_path,
        proxy_enabled=True,
        proxy_gateway_url="http://user-{country}:pass@gateway:8080",
        proxy_gateway_countries="de, us",
        proxy_gateway_default_country="us",
    )
    assert settings.proxy_gateway_countries == "DE,US"
    assert settings.proxy_gateway_country_list == ("DE", "US")


def test_proxy_failure_detection() -> None:
    assert looks_like_proxy_failure(RuntimeError("net::ERR_TUNNEL_CONNECTION_FAILED"))
    assert looks_like_proxy_failure(RuntimeError("net::ERR_PROXY_CONNECTION_FAILED"))
    assert not looks_like_proxy_failure(RuntimeError("net::ERR_NAME_NOT_RESOLVED"))

    class ProxyDetailsError(Exception):
        details = {"proxy_failure": True}

    assert is_proxy_failure(ProxyDetailsError())
    assert not is_proxy_failure(RuntimeError("plain"))


def test_acceptance_country_check_matches_configured_provider(tmp_path: Path) -> None:
    from apps.api.services.proxies import ensure_proxy_country
    from packages.core.errors import AppError

    enabled = _settings(
        tmp_path,
        proxy_enabled=True,
        proxy_static_list="DE|http://de.proxy:8080",
    )
    ensure_proxy_country(enabled, None)
    ensure_proxy_country(enabled, "DE")
    with pytest.raises(AppError) as exc:
        ensure_proxy_country(enabled, "US")
    assert exc.value.status_code == 422

    disabled = _settings(tmp_path, proxy_enabled=False)
    ensure_proxy_country(disabled, None)
    with pytest.raises(AppError):
        ensure_proxy_country(disabled, "DE")


def test_provider_selection_matches_configuration(tmp_path: Path) -> None:
    from apps.worker.providers import build_provider
    from apps.worker.providers.gateway import GatewayProxyProvider
    from apps.worker.providers.static import StaticProxyProvider

    static_settings = _settings(
        tmp_path,
        proxy_enabled=True,
        proxy_static_list="DE|http://de.proxy:8080",
    )
    assert isinstance(build_provider(static_settings), StaticProxyProvider)

    gateway_settings = _settings(
        tmp_path,
        proxy_enabled=True,
        proxy_gateway_url="http://gateway.proxy:8080",
    )
    assert isinstance(build_provider(gateway_settings), GatewayProxyProvider)

    with pytest.raises(ProxyConfigError):
        build_provider(_settings(tmp_path, proxy_enabled=False))
