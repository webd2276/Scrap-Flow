"""Typed, fail-fast application settings.

Every deployment must supply real secrets. There are deliberately no secret
defaults: a missing or short secret is a startup error, not a runtime surprise.
"""

from __future__ import annotations

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
