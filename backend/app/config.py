"""Application configuration settings."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    allow_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        alias="BACKEND_ALLOW_ORIGINS",
        description="Comma separated list of origins authorised for CORS.",
    )
    rate_limit_default: str = Field(
        default="120/minute",
        alias="BACKEND_RATE_LIMIT",
        description="Default rate limit applied to incoming requests.",
    )
    rate_limit_enabled: bool = Field(
        default=True,
        alias="BACKEND_RATE_LIMIT_ENABLED",
        description="Toggle to disable throttling logic altogether.",
    )
    rate_limit_headers_enabled: bool = Field(
        default=True,
        alias="BACKEND_RATE_LIMIT_HEADERS_ENABLED",
        description="Expose rate limit headers on throttled responses.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: str | List[str]) -> List[str]:
        if isinstance(value, str):
            parts = [origin.strip() for origin in value.split(",")]
            origins = [origin for origin in parts if origin]
            return origins or ["http://localhost:3000"]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings."""

    return Settings()
