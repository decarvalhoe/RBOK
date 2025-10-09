"""Pydantic models representing LLM conversations."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class LlmMessage(BaseModel):
    """Single message item in a chat conversation."""

    role: str = Field(..., description="Role of the author (system, user, assistant)")
    content: str = Field(..., description="Text content of the message")


class LlmRequest(BaseModel):
    """Request payload for LLM chat completions."""

    messages: List[LlmMessage] = Field(..., min_length=1)
    model: Optional[str] = Field(
        default=None,
        description="Optional override of the configured chat completion model",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature to apply to the completion",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional limit for generated tokens",
    )


class LlmResponse(BaseModel):
    """Response payload for chat completions."""

    content: str = Field(..., description="Assistant message produced by the model")
    model: str = Field(..., description="Model that generated the response")
    finish_reason: Optional[str] = Field(
        default=None, description="Reason returned by the provider for finishing"
    )
    usage: Optional[dict] = Field(
        default=None, description="Token usage metadata reported by the provider"
    )
