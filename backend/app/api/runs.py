"""Procedure run management endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import models
from app.auth import User, get_current_user, get_opa_client
from app.database import get_db
from app.services.procedures import ProcedureFSM
from app.services.procedures.exceptions import (
    ChecklistValidationError,
    InvalidTransitionError,
    SlotValidationError,
    StepNotFoundError,
    StepOrderError,
)

router = APIRouter(prefix="/runs", tags=["procedure-runs"])


class RunCreate(BaseModel):
    procedure_id: str
    user_id: Optional[str] = None


class RunResponse(BaseModel):
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class RunStepPayload(BaseModel):
    slots: Dict[str, Any] = Field(default_factory=dict)
    checklist: List[Dict[str, Any]] | Dict[str, Any] | None = None


class RunStepResponse(BaseModel):
    id: str
    run_id: str
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime
    run_state: str

    model_config = ConfigDict(from_attributes=True)


def _evaluate_policy(user: User, action: str, resource: Optional[str]) -> None:
    client = get_opa_client()
    if client is None:
        return
    evaluation = client.evaluate(
        {
            "input": {
                "subject": {
                    "id": user.subject,
                    "username": user.username,
                    "roles": list(user.roles),
                },
                "action": action,
                "resource": resource,
            }
        }
    )
    decision = evaluation.get("result")
    allowed = False
    if isinstance(decision, dict):
        allowed = bool(decision.get("allow", False))
    elif isinstance(decision, bool):
        allowed = decision
    if not allowed:
        reason = None
        if isinstance(decision, dict):
            reason = decision.get("reason")
        detail = str(reason) if reason else "Access denied by policy"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunResponse:
    procedure = db.get(models.Procedure, payload.procedure_id)
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")

    _evaluate_policy(current_user, "runs:create", procedure.id)

    run = models.ProcedureRun(
        procedure_id=procedure.id,
        user_id=payload.user_id or current_user.subject,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return RunResponse.model_validate(run)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> RunResponse:
    run = db.get(models.ProcedureRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return RunResponse.model_validate(run)


@router.post("/{run_id}/steps/{step_key}/commit", response_model=RunStepResponse)
def commit_step(
    run_id: str,
    step_key: str,
    payload: RunStepPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunStepResponse:
    run = db.get(models.ProcedureRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if run.procedure_id != payload.slots.get("procedure_id", run.procedure_id):
        # Prevent cross-procedure tampering when slots contain procedure references
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid procedure context")

    _evaluate_policy(current_user, "runs:commit_step", run.procedure_id)

    fsm = ProcedureFSM(db)
    try:
        state = fsm.commit_step(run, step_key, payload.slots, payload.checklist)
        db.commit()
        db.refresh(run)
        db.refresh(state)
    except StepNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StepOrderError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (SlotValidationError, ChecklistValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return RunStepResponse(
        id=state.id,
        run_id=state.run_id,
        step_key=state.step_key,
        payload=state.payload,
        committed_at=state.committed_at,
        run_state=run.state,
    )


__all__ = [
    "router",
    "RunCreate",
    "RunResponse",
]
