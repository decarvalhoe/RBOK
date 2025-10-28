"""Pydantic schemas describing procedure definitions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProcedureSlot(BaseModel):
    """Definition of a dynamic slot collected while executing a step."""

    name: str = Field(..., description="Unique identifier of the slot inside the step")
    type: str = Field(
        ..., description="Logical type of the slot (string, number, enum, etc.)"
    )
    required: bool = Field(
        default=True, description="Whether the slot must be provided to commit the step"
    )
    label: Optional[str] = Field(
        default=None, description="Human readable label used in user interfaces"
    )
    description: Optional[str] = Field(
        default=None, description="Additional guidance displayed next to the slot"
    )
    validation_rule: Optional[str] = Field(
        default=None,
        validation_alias="validate",
        serialization_alias="validate",
        description="Optional validation hint (regex, rule identifier, …)",
    )
    mask: Optional[str] = Field(
        default=None, description="Input mask applied when collecting the value"
    )
    options: Optional[List[str]] = Field(
        default=None, description="Explicit list of available choices for enumerations"
    )
    position: Optional[int] = Field(
        default=None, description="Ordering index of the slot within the step"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata stored alongside the slot definition",
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def model_dump(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Ensure serialized payloads keep legacy aliases by default."""

        if kwargs.get("mode") == "json" and "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        return super().model_dump(*args, **kwargs)


class ProcedureChecklistItem(BaseModel):
    """Checklist item definition linked to a procedure step."""

    key: str = Field(..., description="Unique identifier of the checklist item")
    label: str = Field(..., description="Label displayed to operators when ticking the item")
    description: Optional[str] = Field(
        default=None,
        description="Supplementary context describing why the item is required",
    )
    required: bool = Field(
        default=False,
        description="Indicates whether the item must be completed to finish the step",
    )
    default_state: Optional[bool] = Field(
        default=None,
        description="Optional default completion state suggested to the operator",
    )
    position: Optional[int] = Field(
        default=None, description="Ordering index amongst the step checklist items"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata associated with the checklist item",
    )

    model_config = ConfigDict(extra="allow")


class ProcedureStepBase(BaseModel):
    """Shared attributes describing a procedure step."""

    key: str = Field(..., description="Unique identifier of the step within the procedure")
    title: str = Field(..., description="Title displayed to the operator")
    prompt: Optional[str] = Field(
        default=None,
        description="Detailed instructions presented when the step is active",
    )
    position: Optional[int] = Field(
        default=None, description="Ordering index of the step inside the procedure"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary metadata associated with the step"
    )
    slots: List[ProcedureSlot] = Field(
        default_factory=list,
        description="Collection of slots required to complete the step",
    )
    checklists: List[ProcedureChecklistItem] = Field(
        default_factory=list,
        description="Legacy alias containing checklist item definitions",
    )
    checklist_items: List[ProcedureChecklistItem] = Field(
        default_factory=list,
        description="Explicit list of checklist items attached to the step",
    )


class ProcedureStepCreate(ProcedureStepBase):
    """Payload used when creating a new step."""

    id: Optional[str] = Field(
        default=None, description="Optional identifier used when upserting steps"
    )


class ProcedureStepUpdate(ProcedureStepBase):
    """Payload used when updating an existing step."""

    id: Optional[str] = Field(
        default=None, description="Identifier of the step to update when provided"
    )


class ProcedureStepResponse(ProcedureStepBase):
    """Representation of a step returned by API responses."""

    id: str = Field(..., description="Stable identifier of the persisted step")

    model_config = ConfigDict(from_attributes=True)


class ProcedureCreate(BaseModel):
    """Payload describing a procedure to create."""

    name: str = Field(..., description="Human readable name of the procedure")
    description: Optional[str] = Field(
        default=None, description="Detailed description of the procedure"
    )
    steps: List[ProcedureStepCreate] = Field(
        default_factory=list,
        description="Ordered collection of steps composing the procedure",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata stored at the procedure level",
    )


class ProcedureUpdate(BaseModel):
    """Partial payload used to update an existing procedure."""

    name: Optional[str] = Field(
        default=None, description="New name assigned to the procedure when provided"
    )
    description: Optional[str] = Field(
        default=None, description="Updated description of the procedure"
    )
    steps: Optional[List[ProcedureStepUpdate]] = Field(
        default=None,
        description="Replacement collection of steps for the procedure",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Replacement metadata dictionary for the procedure",
    )


class ProcedureResponse(BaseModel):
    """Full representation of a persisted procedure."""

    id: str = Field(..., description="Identifier of the procedure")
    name: str = Field(..., description="Human readable name of the procedure")
    description: Optional[str] = Field(
        default=None, description="Detailed description of the procedure"
    )
    steps: List[ProcedureStepResponse] = Field(
        default_factory=list,
        description="Ordered collection of persisted steps",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata stored at the procedure level",
    )

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ProcedureChecklistItem",
    "ProcedureCreate",
    "ProcedureResponse",
    "ProcedureSlot",
    "ProcedureStepCreate",
    "ProcedureStepResponse",
    "ProcedureStepUpdate",
    "ProcedureUpdate",
]
