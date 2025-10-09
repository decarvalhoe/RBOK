"""Pydantic models for ASR interactions."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AsrRequest(BaseModel):
    """Request payload for audio transcription."""

    audio_base64: str = Field(..., description="Audio content encoded in base64")
    audio_format: str = Field(
        "wav",
        min_length=1,
        description="File extension of the encoded audio (e.g. wav, mp3)",
    )
    language: Optional[str] = Field(
        default=None,
        description="Optional BCP-47 language tag to guide transcription",
    )


class AsrResponse(BaseModel):
    """Response payload for transcription results."""

    text: str = Field(..., description="Recognised transcript of the provided audio")
    language: Optional[str] = Field(
        default=None, description="Detected or requested language for the transcript"
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Model confidence in the transcription when available",
    )
