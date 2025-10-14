from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProcedureRun, ProcedureRunChecklistStatus
from ..services.procedures import (
    ChecklistIncompleteError,
    InvalidChecklistItemError,
    ProcedureRunNotFoundError,
    ProcedureRunService,
    ProcedureStepNotFoundError,
)

router = APIRouter(prefix="/runs", tags=["procedure-runs"])


class ChecklistUpdateModel(BaseModel):
    completed_item_ids: List[str] = Field(default_factory=list)


class CommitStepRequest(BaseModel):
    step_key: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    checklist: ChecklistUpdateModel | None = None


class RunStepStateModel(BaseModel):
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunChecklistStatusModel(BaseModel):
    checklist_item_id: str
    step_key: str
    item_key: str
    item_label: str
    completed: bool
    completed_at: datetime | None = None


class ProcedureRunModel(BaseModel):
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: datetime | None = None
    step_states: List[RunStepStateModel]
    checklist_statuses: List[RunChecklistStatusModel]

    model_config = ConfigDict(from_attributes=True)


def _serialize_checklist_status(status: ProcedureRunChecklistStatus) -> RunChecklistStatusModel:
    item = status.checklist_item
    step = item.step
    return RunChecklistStatusModel(
        checklist_item_id=status.checklist_item_id,
        step_key=step.key,
        item_key=item.key,
        item_label=item.label,
        completed=status.completed,
        completed_at=status.completed_at,
    )


def _serialize_run(run: ProcedureRun) -> ProcedureRunModel:
    return ProcedureRunModel(
        id=run.id,
        procedure_id=run.procedure_id,
        user_id=run.user_id,
        state=run.state,
        created_at=run.created_at,
        closed_at=run.closed_at,
        step_states=[RunStepStateModel.model_validate(state) for state in run.step_states],
        checklist_statuses=[_serialize_checklist_status(status) for status in run.checklist_statuses],
    )


@router.get("/{run_id}", response_model=ProcedureRunModel)
def get_run(run_id: str, db: Session = Depends(get_db)) -> ProcedureRunModel:
    service = ProcedureRunService(db)
    try:
        run = service.get_run(run_id)
    except ProcedureRunNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _serialize_run(run)


@router.post("/{run_id}/commit-step", response_model=ProcedureRunModel)
def commit_step(
    run_id: str, request: CommitStepRequest, db: Session = Depends(get_db)
) -> ProcedureRunModel:
    service = ProcedureRunService(db)
    completed_ids: Iterable[str] | None = None
    if request.checklist is not None:
        completed_ids = request.checklist.completed_item_ids
    try:
        run = service.commit_step(
            run_id=run_id,
            step_key=request.step_key,
            payload=request.payload,
            completed_checklist_item_ids=completed_ids,
        )
        db.commit()
    except ProcedureRunNotFoundError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    except ProcedureStepNotFoundError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown step key for procedure"
        )
    except InvalidChecklistItemError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_checklist_items", "invalid_item_ids": exc.invalid_item_ids},
        )
    except ChecklistIncompleteError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "checklist_incomplete", "missing_item_ids": exc.missing_item_ids},
        )

    return _serialize_run(run)


__all__ = ["router"]
