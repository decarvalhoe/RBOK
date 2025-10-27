"""Pydantic schemas describing procedure run payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProcedureRunCreate(BaseModel):
    """Payload used to create a new procedure run."""

    procedure_id: str = Field(..., description="Identifier of the procedure to execute")
    user_id: Optional[str] = Field(
        default=None,
        description="Identifier of the user running the procedure (defaults to caller)",
    )
    state: str = Field(
        default="pending",
        description="Initial FSM state assigned to the run (defaults to pending)",
    )


class RunChecklistItemPayload(BaseModel):
    """Representation of a checklist submission."""

    key: str = Field(..., description="Identifier of the checklist item")
    completed: bool = Field(..., description="Whether the item has been completed")
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp at which the item was completed",
    )


class ProcedureRunStepCommit(BaseModel):
    """Payload used to commit a step during a run."""

    slots: Dict[str, Any] = Field(
        default_factory=dict,
        description="Slot values collected for the committed step",
    )
    checklist: List[RunChecklistItemPayload] = Field(
        default_factory=list,
        description="Checklist submissions associated with the step",
    )


class RunStepState(BaseModel):
    """State snapshot of a committed step."""

    step_key: str = Field(..., description="Key of the committed step")
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Payload recorded during the commit (slots, checklist, etc.)",
    )
    committed_at: datetime = Field(
        ..., description="Timestamp of the commit persisted in the database"
    )

    model_config = ConfigDict(from_attributes=True)


class RunChecklistItemState(BaseModel):
    """Aggregated state of a checklist item for a run."""

    id: str = Field(..., description="Identifier of the checklist item state")
    key: str = Field(..., description="Checklist item key")
    label: Optional[str] = Field(
        default=None, description="Human readable label of the checklist item"
    )
    completed: bool = Field(
        ..., description="Whether the checklist item has been completed"
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="Timestamp at which the item was completed"
    )

    model_config = ConfigDict(from_attributes=True)


class ChecklistProgress(BaseModel):
    """Synthetic metrics describing checklist progression."""

    total: int = Field(..., description="Total number of checklist items")
    completed: int = Field(..., description="Number of completed checklist items")
    percentage: float = Field(..., description="Completion percentage between 0 and 100")


class ProcedureRunResponse(BaseModel):
    """Representation of a persisted procedure run."""

    id: str = Field(..., description="Identifier of the run")
    procedure_id: str = Field(..., description="Identifier of the executed procedure")
    user_id: str = Field(..., description="Identifier of the user associated with the run")
    state: str = Field(..., description="Current FSM state of the run")
    created_at: datetime = Field(..., description="Creation timestamp of the run")
    closed_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the run reached a terminal state"
    )
    procedure: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional embedded procedure representation for convenience",
    )
    step_states: List[RunStepState] = Field(
        default_factory=list,
        description="Committed step states for the run",
    )
    checklist_states: List[RunChecklistItemState] = Field(
        default_factory=list,
        description="Legacy alias exposing checklist item states",
    )
    checklist_statuses: List[RunChecklistItemState] = Field(
        default_factory=list,
        description="List of checklist item states (preferred field)",
    )
    checklist_progress: ChecklistProgress = Field(
        ..., description="Aggregated metrics describing checklist completion"
    )

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ChecklistProgress",
    "ProcedureRunCreate",
    "ProcedureRunResponse",
    "ProcedureRunStepCommit",
    "RunChecklistItemPayload",
    "RunChecklistItemState",
    "RunStepState",
]
