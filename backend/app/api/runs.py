"""FastAPI router handling procedure run lifecycle endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..auth import User, get_current_user
from ..database import get_db
from ..services.procedure_runs import (
    ChecklistValidationError,
    InvalidTransitionError,
    ProcedureNotFoundError,
    ProcedureRunNotFoundError,
    ProcedureRunService,
    RunSnapshot,
    SlotValidationError,
)
from ..services.procedures.cache import cached_run_detail, invalidate_run_cache

router = APIRouter(prefix="/runs", tags=["procedure runs"])


def _service(db: Session = Depends(get_db)) -> ProcedureRunService:
    return ProcedureRunService(db)


class ProcedureRunCreateRequest(BaseModel):
    """Payload used to initialise a new procedure run."""

    procedure_id: str = Field(..., description="Identifier of the procedure to start")
    user_id: Optional[str] = Field(
        default=None, description="Identifier of the user running the procedure"
    )


class RunChecklistItemPayload(BaseModel):
    """Checklist submission payload for a single item."""

    key: str = Field(..., description="Unique identifier of the checklist item")
    completed: bool = Field(..., description="Whether the item has been completed")
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of completion (defaults to now when omitted)",
    )


class ProcedureRunCommitStepRequest(BaseModel):
    """Payload used when committing a step within a run."""

    step_key: str = Field(..., description="Key of the step to commit")
    slots: Dict[str, Any] = Field(
        default_factory=dict,
        description="Slot values collected for the step",
    )
    checklist: List[RunChecklistItemPayload] = Field(
        default_factory=list,
        description="Checklist state associated with the step",
    )


class RunChecklistItemState(BaseModel):
    key: str
    label: Optional[str] = None
    completed: bool
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RunStepStateModel(BaseModel):
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcedureRunModel(BaseModel):
    """Representation returned by run endpoints."""

    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime]
    step_states: List[RunStepStateModel]
    checklist_states: List[RunChecklistItemState]

    model_config = ConfigDict(from_attributes=True)


def _serialize_run(snapshot: RunSnapshot) -> ProcedureRunModel:
    run = snapshot.run
    step_states = [
        RunStepStateModel(
            step_key=state.step_key,
            payload=dict(state.payload or {}),
            committed_at=state.committed_at,
        )
        for state in sorted(snapshot.step_states.values(), key=lambda item: item.committed_at)
    ]
    checklist_states = [
        RunChecklistItemState(
            key=status.checklist_item.key,
            label=status.checklist_item.label,
            completed=status.is_completed,
            completed_at=status.completed_at,
        )
        for status in sorted(
            run.checklist_states,
            key=lambda entry: (entry.checklist_item.position, entry.checklist_item.key),
        )
    ]
    return ProcedureRunModel(
        id=run.id,
        procedure_id=run.procedure_id,
        user_id=run.user_id,
        state=run.state,
        created_at=run.created_at,
        closed_at=run.closed_at,
        step_states=step_states,
        checklist_states=checklist_states,
    )


@router.post("", response_model=ProcedureRunModel, status_code=status.HTTP_201_CREATED)
async def start_run(
    payload: ProcedureRunCreateRequest,
    service: ProcedureRunService = Depends(_service),
    current_user: User = Depends(get_current_user),
) -> ProcedureRunModel:
    """Start a new run for the given procedure."""

    user_id = payload.user_id or current_user.subject
    try:
        run = service.start_run(
            procedure_id=payload.procedure_id,
            user_id=user_id,
            actor=current_user.username or current_user.subject,
        )
    except ProcedureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc), "procedure_id": exc.procedure_id},
        ) from exc

    snapshot = service.get_snapshot(run.id)
    return _serialize_run(snapshot)


@router.get("/{run_id}", response_model=ProcedureRunModel)
async def get_run(
    run_id: str,
    service: ProcedureRunService = Depends(_service),
    current_user: User = Depends(get_current_user),
) -> ProcedureRunModel:
    """Return the state of a specific procedure run."""

    try:
        payload = cached_run_detail(
            run_id,
            lambda: _serialize_run(service.get_snapshot(run_id)).model_dump(mode="json"),
        )
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc

    return ProcedureRunModel.model_validate(payload)


@router.post("/{run_id}/commit-step", response_model=ProcedureRunModel)
async def commit_step(
    run_id: str,
    payload: ProcedureRunCommitStepRequest,
    service: ProcedureRunService = Depends(_service),
    current_user: User = Depends(get_current_user),
) -> ProcedureRunModel:
    """Commit a step payload and advance the run state when appropriate."""

    try:
        snapshot = service.commit_step(
            run_id=run_id,
            step_key=payload.step_key,
            slots=payload.slots,
            checklist=[item.model_dump() for item in payload.checklist],
            actor=current_user.username or current_user.subject,
        )
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc
    except SlotValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "issues": exc.issues},
        ) from exc
    except ChecklistValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "issues": exc.issues},
        ) from exc

    invalidate_run_cache(run_id)
    return _serialize_run(snapshot)

