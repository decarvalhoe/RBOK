"""FastAPI router for procedure run lifecycle management."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

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


router = APIRouter(prefix="/runs", tags=["procedure runs"])


def _service(db: Session = Depends(get_db)) -> ProcedureRunService:
    return ProcedureRunService(db)


class ProcedureRunCreateRequest(BaseModel):
    procedure_id: str = Field(..., description="Identifier of the procedure to start")
    user_id: Optional[str] = Field(
        default=None, description="Identifier of the user running the procedure"
    )


class RunChecklistItemPayload(BaseModel):
    key: str = Field(..., description="Unique identifier of the checklist item")
    label: Optional[str] = Field(
        default=None, description="Human-readable label for the checklist item"
    )
    completed: bool = Field(..., description="Whether the item has been completed")
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of completion (defaults to now when omitted)",
    )


class ProcedureRunCommitStepRequest(BaseModel):
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


class ProcedureRunStepStateResponse(BaseModel):
    key: str
    title: str
    prompt: str
    status: str
    collected_slots: Dict[str, Any]
    checklist: List[RunChecklistItemState]
    committed_at: Optional[datetime] = None


class ProcedureRunDetailResponse(BaseModel):
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime]
    current_step: Optional[str]
    steps: List[ProcedureRunStepStateResponse]

    model_config = ConfigDict(from_attributes=True)


def _parse_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    value = raw
    if raw.endswith("Z"):
        value = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_response(snapshot: RunSnapshot) -> ProcedureRunDetailResponse:
    run = snapshot.run
    procedure_steps = sorted(run.procedure.steps, key=lambda step: step.position)
    pending_steps = [step for step in procedure_steps if step.key not in snapshot.step_states]
    current_step_key = pending_steps[0].key if pending_steps else None

    responses: List[ProcedureRunStepStateResponse] = []
    for step in procedure_steps:
        state = snapshot.step_states.get(step.key)
        if state:
            payload = state.payload or {}
            slots = payload.get("slots") or {}
            raw_checklist = payload.get("checklist") or []
            checklist_items = [
                RunChecklistItemState(
                    key=item.get("key", ""),
                    label=item.get("label"),
                    completed=bool(item.get("completed", False)),
                    completed_at=_parse_timestamp(item.get("completed_at")),
                )
                for item in raw_checklist
                if item
            ]
            responses.append(
                ProcedureRunStepStateResponse(
                    key=step.key,
                    title=step.title,
                    prompt=step.prompt,
                    status="completed",
                    collected_slots=slots,
                    checklist=checklist_items,
                    committed_at=state.committed_at,
                )
            )
        else:
            status_value = "pending"
            if current_step_key == step.key and run.state != "completed":
                status_value = "in_progress"
            responses.append(
                ProcedureRunStepStateResponse(
                    key=step.key,
                    title=step.title,
                    prompt=step.prompt,
                    status=status_value,
                    collected_slots={},
                    checklist=[],
                    committed_at=None,
                )
            )

    return ProcedureRunDetailResponse(
        id=run.id,
        procedure_id=run.procedure_id,
        user_id=run.user_id,
        state=run.state,
        created_at=run.created_at,
        closed_at=run.closed_at,
        current_step=current_step_key,
        steps=responses,
    )


@router.post("", response_model=ProcedureRunDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: ProcedureRunCreateRequest,
    service: ProcedureRunService = Depends(_service),
) -> ProcedureRunDetailResponse:
    user_id = payload.user_id or "anonymous"
    try:
        run = service.start_run(
            procedure_id=payload.procedure_id,
            user_id=user_id,
            actor=user_id,
        )
    except ProcedureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "procedure_not_found", "procedure_id": exc.procedure_id},
        ) from exc

    snapshot = service.get_snapshot(run.id)
    return _build_response(snapshot)


@router.get("/{run_id}", response_model=ProcedureRunDetailResponse)
async def get_run(
    run_id: str,
    service: ProcedureRunService = Depends(_service),
) -> ProcedureRunDetailResponse:
    try:
        snapshot = service.get_snapshot(run_id)
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "run_not_found", "run_id": exc.run_id},
        ) from exc
    return _build_response(snapshot)


@router.post("/{run_id}/commit-step", response_model=ProcedureRunDetailResponse)
async def commit_step(
    run_id: str,
    payload: ProcedureRunCommitStepRequest,
    service: ProcedureRunService = Depends(_service),
) -> ProcedureRunDetailResponse:
    try:
        snapshot = service.commit_step(
            run_id=run_id,
            step_key=payload.step_key,
            slots=payload.slots,
            checklist=[item.model_dump(mode="python") for item in payload.checklist],
            actor=None,
        )
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "run_not_found", "run_id": exc.run_id},
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "invalid_transition", "message": str(exc)},
        ) from exc
    except SlotValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "slot_validation_failed", "issues": exc.issues},
        ) from exc
    except ChecklistValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "checklist_validation_failed", "issues": exc.issues},
        ) from exc

    return _build_response(snapshot)


__all__ = ["router"]
