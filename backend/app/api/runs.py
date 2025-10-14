"""REST API endpoints for procedure runs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Procedure, ProcedureRun, ProcedureRunStepState
from ..schemas.runs import ProcedureRunCreate, ProcedureRunResponse, ProcedureRunStepCommit
from ..services.procedures import cached_run_detail, invalidate_run_cache
from ..utils.serialization import serialize_run

logger = structlog.get_logger(__name__)

router = APIRouter()


def _get_run_or_404(run_id: str, db: Session) -> ProcedureRun:
    run = (
        db.query(ProcedureRun)
        .options(selectinload(ProcedureRun.procedure).selectinload(Procedure.steps))
        .filter(ProcedureRun.id == run_id)
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/runs", response_model=ProcedureRunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(payload: ProcedureRunCreate, db: Session = Depends(get_db)) -> ProcedureRunResponse:
    """Create a new procedure run."""

    procedure = db.query(Procedure).filter(Procedure.id == payload.procedure_id).one_or_none()
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")

    run = ProcedureRun(
        procedure_id=payload.procedure_id,
        user_id=payload.user_id,
        state=payload.state,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run.procedure = procedure

    logger.info("procedure_run_created", run_id=run.id, procedure_id=run.procedure_id)
    invalidate_run_cache(run.id)

    return ProcedureRunResponse(**serialize_run(run, []))


@router.get("/runs/{run_id}", response_model=ProcedureRunResponse)
async def get_run(run_id: str, db: Session = Depends(get_db)) -> ProcedureRunResponse:
    """Return the details of a procedure run, cached when possible."""

    def fetch() -> Dict[str, Any]:
        run = _get_run_or_404(run_id, db)
        states: List[ProcedureRunStepState] = (
            db.query(ProcedureRunStepState)
            .filter(ProcedureRunStepState.run_id == run.id)
            .order_by(ProcedureRunStepState.committed_at)
            .all()
        )
        return serialize_run(run, states)

    payload = cached_run_detail(run_id, fetch)
    return ProcedureRunResponse(**payload)


@router.post(
    "/runs/{run_id}/steps/{step_key}/commit",
    response_model=ProcedureRunResponse,
    status_code=status.HTTP_200_OK,
)
async def commit_step(
    run_id: str,
    step_key: str,
    payload: ProcedureRunStepCommit,
    db: Session = Depends(get_db),
) -> ProcedureRunResponse:
    """Persist the payload for a given step and invalidate the run cache."""

    run = _get_run_or_404(run_id, db)

    state = (
        db.query(ProcedureRunStepState)
        .filter(
            ProcedureRunStepState.run_id == run_id,
            ProcedureRunStepState.step_key == step_key,
        )
        .one_or_none()
    )
    if state is None:
        state = ProcedureRunStepState(run_id=run_id, step_key=step_key, payload=payload.payload)
        db.add(state)
    else:
        state.payload = payload.payload
        state.committed_at = datetime.utcnow()

    db.commit()

    logger.info("procedure_run_step_committed", run_id=run_id, step_key=step_key)
    invalidate_run_cache(run_id)

    states: List[ProcedureRunStepState] = (
        db.query(ProcedureRunStepState)
        .filter(ProcedureRunStepState.run_id == run_id)
        .order_by(ProcedureRunStepState.committed_at)
        .all()
    )
    return ProcedureRunResponse(**serialize_run(run, states))


__all__ = ["router"]
