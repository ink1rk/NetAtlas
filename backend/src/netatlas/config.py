"""Application settings loaded exclusively from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NETATLAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NetAtlas"
    version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "production"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = Field(
        default="postgresql+asyncpg://netatlas:netatlas@postgres:5432/netatlas"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://netatlas:netatlas@postgres:5432/netatlas"
    )
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://netatlas:netatlas@rabbitmq:5672//"

    # 32-byte key, base64-encoded
    master_key_b64: SecretStr = Field(default=SecretStr(""))
    jwt_private_key_pem: SecretStr = Field(default=SecretStr(""))
    jwt_public_key_pem: SecretStr = Field(default=SecretStr(""))
    jwt_algorithm: str = "RS256"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 7

    cors_origins: list[str] = Field(default_factory=lambda: [])
    rate_limit_login_per_minute: int = 10
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: SecretStr = Field(default=SecretStr(""))
    bootstrap_admin_email: str = "admin@netatlas.local"

    discovery_max_concurrency: int = 32
    discovery_icmp_timeout: float = 1.0
    discovery_snmp_timeout: float = 2.0
    metrics_interval_seconds: int = 60

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if not value.strip():
                return []
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
