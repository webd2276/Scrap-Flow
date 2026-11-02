"""Typed, fail-fast application settings.

Every deployment must supply real secrets. There are deliberately no secret
defaults: a missing or short secret is a startup error, not a runtime surprise.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "ScrapeFlow"
    app_env: Environment = "development"
    app_version: str = "0.1.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    public_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"

    database_url: str
    redis_url: str

    api_key_pepper: SecretStr = Field(min_length=32)
    jwt_secret: SecretStr = Field(min_length=32)
    webhook_secret_key: SecretStr = Field(min_length=32)

    request_id_header: str = "X-Request-ID"
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=10)

    database_pool_size: int = Field(default=10, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=50)

    jwt_access_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    jwt_refresh_ttl_days: int = Field(default=30, ge=1, le=90)
    jwt_active_kid: str = Field(default="primary", pattern=r"^[A-Za-z0-9_-]{1,16}$")
    jwt_previous_keys: SecretStr | None = None
    password_min_length: int = Field(default=12, ge=8, le=128)
    tos_version: str = "2026-10-30"

    rate_limit_org_per_minute: int = Field(default=120, ge=1, le=10000)
    rate_limit_org_burst: int = Field(default=120, ge=1, le=10000)
    rate_limit_ip_per_minute: int = Field(default=60, ge=1, le=10000)
    rate_limit_ip_burst: int = Field(default=60, ge=1, le=10000)
    rate_limit_auth_per_minute: int = Field(default=10, ge=1, le=1000)
    rate_limit_auth_burst: int = Field(default=10, ge=1, le=1000)

    queue_enabled: bool = True
    job_timeout_seconds: int = Field(default=120, ge=10, le=900)
    job_lease_seconds: int = Field(default=180, ge=30, le=1800)
    job_max_attempts: int = Field(default=2, ge=1, le=5)
    job_reaper_interval_seconds: int = Field(default=30, ge=5, le=300)
    job_queued_stale_seconds: int = Field(default=60, ge=10, le=600)
    http_timeout_seconds: float = Field(default=30, gt=0, le=120)
    http_max_bytes: int = Field(default=5_000_000, ge=1024, le=20_000_000)
    http_max_redirects: int = Field(default=5, ge=0, le=10)
    http_user_agent: str = "ScrapeFlowBot/0.1 (+https://scrapeflow.example/bot)"

    egress_proxy_url: str | None = None
    egress_proxy_listen_host: str = "127.0.0.1"
    egress_proxy_listen_port: int = Field(default=8888, ge=1, le=65535)
    egress_allowed_ports: str = "80,443,8080,8443"
    egress_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    egress_idle_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    egress_max_header_bytes: int = Field(default=32_768, ge=1024, le=131_072)

    browser_headless: bool = True
    browser_no_sandbox: bool = False
    browser_page_load_timeout_seconds: int = Field(default=60, ge=5, le=300)
    session_registry_ttl_seconds: int = Field(default=900, ge=60, le=3600)

    automation_max_steps: int = Field(default=100, ge=1, le=500)
    automation_max_depth: int = Field(default=3, ge=1, le=5)
    automation_max_secret_bytes: int = Field(default=16_384, ge=0, le=1_048_576)
    automation_secret_key: SecretStr | None = Field(default=None, min_length=32)
    automation_secrets_ttl_seconds: int = Field(default=960, ge=60, le=7200)

    artifacts_local_dir: str = "var/artifacts"
    artifacts_retention_days: int = Field(default=7, ge=1, le=365)
    artifacts_max_bytes: int = Field(default=10_000_000, ge=1024, le=100_000_000)
    artifact_presign_seconds: int = Field(default=300, ge=60, le=3600)

    selenium_remote_url: str | None = None
    artifacts_endpoint: str | None = None
    artifacts_bucket: str = "scrapeflow"
    artifacts_access_key: SecretStr | None = None
    artifacts_secret_key: SecretStr | None = None
    artifacts_region: str = "us-east-1"
    artifacts_use_ssl: bool = False

    sentry_dsn: str | None = None
    metrics_enabled: bool = True

    billing_enabled: bool = False
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    stripe_price_starter: str | None = None
    stripe_price_pro: str | None = None
    stripe_price_business: str | None = None

    @field_validator(
        "selenium_remote_url",
        "artifacts_endpoint",
        "artifacts_access_key",
        "artifacts_secret_key",
        "sentry_dsn",
        "egress_proxy_url",
        "automation_secret_key",
        "stripe_secret_key",
        "stripe_webhook_secret",
        "stripe_price_starter",
        "stripe_price_pro",
        "stripe_price_business",
        mode="before",
    )
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        if value.startswith(("postgres://", "postgresql://")):
            return value.replace("postgres://", "postgresql+asyncpg://", 1).replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        return value

    @field_validator("redis_url")
    @classmethod
    def _validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("REDIS_URL must be a Redis URL")
        return value

    @field_validator("egress_proxy_url")
    @classmethod
    def _validate_egress_proxy_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("EGRESS_PROXY_URL must be an http(s) proxy URL")
        return value.rstrip("/")

    @field_validator("egress_allowed_ports")
    @classmethod
    def _validate_allowed_ports(cls, value: str) -> str:
        ports = [part.strip() for part in value.split(",") if part.strip()]
        if not ports:
            raise ValueError("EGRESS_ALLOWED_PORTS must list at least one port")
        for port in ports:
            if not port.isdigit() or not 1 <= int(port) <= 65535:
                raise ValueError(f"Invalid egress port: {port}")
        return ",".join(ports)

    @field_validator("public_base_url")
    @classmethod
    def _validate_public_base_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("PUBLIC_BASE_URL must be http(s)")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _billing_requires_stripe(self) -> Settings:
        if self.billing_enabled and (
            self.stripe_secret_key is None or self.stripe_webhook_secret is None
        ):
            raise ValueError("BILLING_ENABLED requires STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET")
        return self

    @model_validator(mode="after")
    def _validate_jwt_keyring(self) -> Settings:
        """Reject malformed rotation keys at startup, not on first request."""
        previous = self.jwt_previous_key_map
        if self.jwt_active_kid in previous:
            raise ValueError("JWT_ACTIVE_KID must not also appear in JWT_PREVIOUS_KEYS")
        return self

    @model_validator(mode="after")
    def _validate_job_timing(self) -> Settings:
        if self.job_lease_seconds < self.job_timeout_seconds + 30:
            raise ValueError("JOB_LEASE_SECONDS must be at least JOB_TIMEOUT_SECONDS + 30")
        if self.automation_secrets_ttl_seconds < self.job_timeout_seconds + 60:
            raise ValueError(
                "AUTOMATION_SECRETS_TTL_SECONDS must be at least JOB_TIMEOUT_SECONDS + 60"
            )
        return self

    @model_validator(mode="after")
    def _production_requires_object_storage(self) -> Settings:
        if self.is_production and self.artifacts_endpoint is None:
            raise ValueError("Production requires ARTIFACTS_ENDPOINT (S3/MinIO)")
        return self

    @property
    def egress_port_set(self) -> frozenset[int]:
        return frozenset(int(part) for part in self.egress_allowed_ports.split(",") if part)

    @property
    def jwt_previous_key_map(self) -> dict[str, str]:
        if self.jwt_previous_keys is None:
            return {}
        try:
            parsed = json.loads(self.jwt_previous_keys.get_secret_value())
        except json.JSONDecodeError as exc:
            raise ValueError("JWT_PREVIOUS_KEYS must be a JSON object of kid -> secret") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JWT_PREVIOUS_KEYS must be a JSON object of kid -> secret")
        mapping: dict[str, str] = {}
        for kid, secret in parsed.items():
            if not isinstance(kid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", kid):
                raise ValueError("JWT previous key ids must match [A-Za-z0-9_-]{1,16}")
            if not isinstance(secret, str) or len(secret) < 32:
                raise ValueError("Every JWT previous secret must be at least 32 characters")
            mapping[kid] = secret
        return mapping

    @property
    def jwt_keyring(self) -> dict[str, str]:
        keys = {self.jwt_active_kid: self.jwt_secret.get_secret_value()}
        keys.update(self.jwt_previous_key_map)
        return keys

    @property
    def cors_origin_list(self) -> tuple[str, ...]:
        return tuple(origin.strip() for origin in self.cors_origins.split(",") if origin.strip())

    @property
    def asyncpg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once. Raises ``ValidationError`` on missing/short secrets."""
    return Settings()
