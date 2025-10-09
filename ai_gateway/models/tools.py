"""Pydantic schemas for tool orchestration endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SlotDefinition(BaseModel):
    """Definition of a slot required to complete a procedure step."""

    name: str = Field(..., description="Unique slot identifier")
    label: Optional[str] = Field(default=None, description="Human readable label")
    type: Optional[str] = Field(default=None, description="Type hint for the slot value")
    required: bool = Field(default=False, description="Whether the slot must be provided")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata provided by the backend",
    )


class GetRequiredSlotsRequest(BaseModel):
    procedure_id: str = Field(..., description="Identifier of the target procedure")
    step_key: str = Field(..., description="Key of the step to inspect")


class GetRequiredSlotsResponse(BaseModel):
    slots: List[SlotDefinition] = Field(..., description="List of slot definitions")


class ValidateSlotRequest(BaseModel):
    procedure_id: str = Field(...)
    step_key: str = Field(...)
    slot_name: str = Field(...)
    value: Any = Field(..., description="Value provided by the user for the slot")


class ValidateSlotResponse(BaseModel):
    is_valid: bool = Field(..., description="Whether the provided value is acceptable")
    reason: Optional[str] = Field(
        default=None, description="Optional explanation when the value is invalid"
    )


class CommitStepRequest(BaseModel):
    run_id: str = Field(..., description="Identifier of the procedure run")
    step_key: str = Field(..., description="Key of the completed step")
    slots: Dict[str, Any] = Field(
        default_factory=dict,
        description="Collected slot values to persist for the step",
    )


class CommitStepResponse(BaseModel):
    status: str = Field(..., description="Acknowledgement status returned by the backend")
    run_id: str = Field(...)
    step_key: str = Field(...)
    slots: Dict[str, Any] = Field(...)
    run_state: Optional[str] = Field(default=None)
