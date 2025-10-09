"""Configuration utilities for the AI gateway service."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    """Application settings loaded from environment variables."""

    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_asr_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    backend_base_url: str = "http://localhost:8000"
    allowed_origins: List[str] = Field(default_factory=lambda: ["*"])

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: List[str] | str) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        data = {
            "openai_api_key": os.getenv("AI_GATEWAY_OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY"),
            "openai_model": os.getenv("AI_GATEWAY_OPENAI_MODEL", "gpt-4o-mini"),
            "openai_asr_model": os.getenv(
                "AI_GATEWAY_OPENAI_ASR_MODEL", "gpt-4o-mini-transcribe"
            ),
            "openai_tts_model": os.getenv(
                "AI_GATEWAY_OPENAI_TTS_MODEL", "gpt-4o-mini-tts"
            ),
            "openai_tts_voice": os.getenv(
                "AI_GATEWAY_OPENAI_TTS_VOICE", "alloy"
            ),
            "backend_base_url": os.getenv(
                "AI_GATEWAY_BACKEND_BASE_URL", "http://localhost:8000"
            ),
            "allowed_origins": os.getenv("AI_GATEWAY_ALLOWED_ORIGINS", "*"),
        }
        return cls(**data)


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""

    settings = Settings.from_env()
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI API key must be provided via AI_GATEWAY_OPENAI_API_KEY or OPENAI_API_KEY"
        )
    return settings
