"""Pydantic models for text-to-speech interactions."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TtsRequest(BaseModel):
    """Request payload for synthesising speech from text."""

    text: str = Field(..., min_length=1, description="Text to synthesise")
    voice: Optional[str] = Field(
        default=None, description="Voice preset identifier supported by the provider"
    )
    audio_format: str = Field(
        "mp3",
        description="Desired response audio format (e.g. mp3, wav)",
        min_length=2,
    )


class TtsResponse(BaseModel):
    """Response payload for text-to-speech conversions."""

    audio_base64: str = Field(..., description="Synthesised audio encoded in base64")
    audio_format: str = Field(..., description="Format of the encoded audio")
    voice: Optional[str] = Field(default=None, description="Voice preset that was used")
