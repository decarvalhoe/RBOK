"""Pydantic models for procedure API payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProcedureMetadata(BaseModel):
    """Loose metadata attached to a procedure definition."""

    model_config = ConfigDict(extra="allow")


class ProcedureStepMetadata(BaseModel):
    """Arbitrary metadata associated with a procedure step."""

    model_config = ConfigDict(extra="allow")


class ProcedureSlot(BaseModel):
    """Describe a slot to be collected within a step."""

    name: str
    type: str
    required: bool = True
    label: Optional[str] = None
    description: Optional[str] = None
    validate: Optional[str] = None
    mask: Optional[str] = None
    options: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ProcedureChecklistItem(BaseModel):
    """Checklist items that can be ticked during a run."""

    key: str
    label: str
    description: Optional[str] = None
    required: bool = False
    default_state: Optional[bool] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ProcedureStepBase(BaseModel):
    """Common fields shared across step input/output models."""

    key: str
    title: str
    prompt: Optional[str] = None
    position: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    slots: List[ProcedureSlot] = Field(default_factory=list)
    checklists: List[ProcedureChecklistItem] = Field(default_factory=list)


class ProcedureStepCreate(ProcedureStepBase):
    """Payload used when creating or updating procedure steps."""

    id: Optional[str] = None


class ProcedureStepResponse(ProcedureStepBase):
    """Representation of a persisted step."""

    id: str

    model_config = ConfigDict(from_attributes=True)


class ProcedureBase(BaseModel):
    """Shared fields between create and response representations."""

    name: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProcedureCreateRequest(ProcedureBase):
    """Incoming payload for the ``POST /procedures`` endpoint."""

    id: Optional[str] = None
    steps: List[ProcedureStepCreate] = Field(default_factory=list)


class ProcedureResponse(ProcedureBase):
    """Full representation returned by procedure endpoints."""

    id: str
    steps: List[ProcedureStepResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ProcedureChecklistItem",
    "ProcedureCreateRequest",
    "ProcedureMetadata",
    "ProcedureResponse",
    "ProcedureSlot",
    "ProcedureStepCreate",
    "ProcedureStepMetadata",
    "ProcedureStepResponse",
]
