"""REST API for procedure management."""
from __future__ import annotations

from typing import List

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Procedure, ProcedureStep
from ..services.procedures import cached_procedure_list, invalidate_procedure_cache
from ..utils.serialization import serialize_procedure
from ..schemas.procedures import ProcedureCreate, ProcedureResponse, ProcedureUpdate

logger = structlog.get_logger(__name__)
"""Procedural workflow endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..database import get_db
from ..services import audit

router = APIRouter()


@router.get("/procedures", response_model=List[ProcedureResponse])
async def list_procedures(db: Session = Depends(get_db)) -> List[ProcedureResponse]:
    """Return the list of procedures, leveraging the Redis cache."""

    def fetch() -> List[dict]:
        procedures: List[Procedure] = (
            db.query(Procedure)
            .options(selectinload(Procedure.steps))
            .order_by(Procedure.name)
            .all()
        )
        return [serialize_procedure(procedure) for procedure in procedures]

    payload = cached_procedure_list(fetch)
    return [ProcedureResponse(**item) for item in payload]


@router.post("/procedures", response_model=ProcedureResponse, status_code=status.HTTP_201_CREATED)
async def create_procedure(
    payload: ProcedureCreate,
    db: Session = Depends(get_db),
) -> ProcedureResponse:
    """Create a new procedure and invalidate the cached list."""

    procedure = Procedure(name=payload.name, description=payload.description)
    for index, step in enumerate(payload.steps):
        procedure.steps.append(
            ProcedureStep(
class ProcedureStepInput(BaseModel):
    """Schema describing a step provided during procedure creation."""

    key: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    slots: List[Dict[str, Any]] = Field(default_factory=list)
    position: Optional[int] = None


class ProcedureCreateRequest(BaseModel):
    """Payload used to create a new procedure."""

    actor: str = Field(..., min_length=1)
    id: Optional[str] = None
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    steps: List[ProcedureStepInput]


class ProcedureStepResponse(BaseModel):
    """Representation of a stored procedure step."""

    id: str
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, Any]]
    position: int


class ProcedureResponse(BaseModel):
    """Representation of a stored procedure including ordered steps."""

    id: str
    name: str
    description: str
    steps: List[ProcedureStepResponse]


class ProcedureRunCreateRequest(BaseModel):
    """Payload used to create a new run for a procedure."""

    actor: str = Field(..., min_length=1)
    procedure_id: str = Field(..., min_length=1)
    user_id: Optional[str] = None


class ProcedureRunResponse(BaseModel):
    """Representation of a run associated with a procedure."""

    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime]


class ProcedureRunStepStateResponse(BaseModel):
    """Representation of the committed payload for a specific step."""

    id: str
    run_id: str
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime


class StepCommitRequest(BaseModel):
    """Payload describing a step commitment during a run."""

    actor: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)


class StepCommitResponse(BaseModel):
    """Response returned after committing a step."""

    run: ProcedureRunResponse
    step_state: ProcedureRunStepStateResponse


class AuditEventResponse(BaseModel):
    """Representation of a stored audit trail event."""

    id: str
    actor: str
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str
    payload_diff: Dict[str, Any]


def _ordered_steps(procedure: models.Procedure) -> List[models.ProcedureStep]:
    return sorted(procedure.steps, key=lambda item: (item.position, item.id))


def _serialise_procedure(procedure: models.Procedure) -> Dict[str, Any]:
    return {
        'id': procedure.id,
        'name': procedure.name,
        'description': procedure.description,
        'steps': [
            {
                'id': step.id,
                'key': step.key,
                'title': step.title,
                'prompt': step.prompt,
                'slots': step.slots,
                'position': step.position,
            }
            for step in _ordered_steps(procedure)
        ],
    }


def _serialise_run(run: models.ProcedureRun) -> Dict[str, Any]:
    return {
        'id': run.id,
        'procedure_id': run.procedure_id,
        'user_id': run.user_id,
        'state': run.state,
        'created_at': run.created_at.isoformat(),
        'closed_at': run.closed_at.isoformat() if run.closed_at else None,
    }


def _serialise_step_state(state: models.ProcedureRunStepState) -> Dict[str, Any]:
    return {
        'id': state.id,
        'run_id': state.run_id,
        'step_key': state.step_key,
        'payload': state.payload,
        'committed_at': state.committed_at.isoformat(),
    }


def _to_procedure_response(procedure: models.Procedure) -> ProcedureResponse:
    return ProcedureResponse(
        id=procedure.id,
        name=procedure.name,
        description=procedure.description,
        steps=[
            ProcedureStepResponse(
                id=step.id,
                key=step.key,
                title=step.title,
                prompt=step.prompt,
                slots=step.slots,
                position=step.position if step.position is not None else index,
            )
        )

    db.add(procedure)
    db.commit()
    db.refresh(procedure)

    invalidate_procedure_cache(procedure.id)

    logger.info("procedure_created", procedure_id=procedure.id)
    return ProcedureResponse(**serialize_procedure(procedure))


@router.put("/procedures/{procedure_id}", response_model=ProcedureResponse)
async def update_procedure(
    procedure_id: str,
    payload: ProcedureUpdate,
    db: Session = Depends(get_db),
) -> ProcedureResponse:
    """Update an existing procedure and invalidate related cache entries."""

    procedure: Procedure | None = (
        db.query(Procedure)
        .options(selectinload(Procedure.steps))
        .filter(Procedure.id == procedure_id)
        .one_or_none()
    )
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")

    if payload.name is not None:
        procedure.name = payload.name
    if payload.description is not None:
        procedure.description = payload.description

    if payload.steps is not None:
        procedure.steps.clear()
        for index, step in enumerate(payload.steps):
            procedure.steps.append(
                ProcedureStep(
                    key=step.key,
                    title=step.title,
                    prompt=step.prompt,
                    slots=step.slots,
                    position=step.position if step.position is not None else index,
                )
            )

    db.add(procedure)
    db.commit()
    db.refresh(procedure)

    invalidate_procedure_cache(procedure.id)

    logger.info("procedure_updated", procedure_id=procedure.id)
    return ProcedureResponse(**serialize_procedure(procedure))


@router.delete("/procedures/{procedure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_procedure(procedure_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a procedure and invalidate cached list."""

    procedure: Procedure | None = db.query(Procedure).filter(Procedure.id == procedure_id).one_or_none()
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")

    db.delete(procedure)
    db.commit()

    invalidate_procedure_cache(procedure_id)
    logger.info("procedure_deleted", procedure_id=procedure_id)


__all__ = ["router"]
                position=step.position,
            )
            for step in _ordered_steps(procedure)
        ],
    )


def _to_run_response(run: models.ProcedureRun) -> ProcedureRunResponse:
    return ProcedureRunResponse(
        id=run.id,
        procedure_id=run.procedure_id,
        user_id=run.user_id,
        state=run.state,
        created_at=run.created_at,
        closed_at=run.closed_at,
    )


def _to_step_state_response(state: models.ProcedureRunStepState) -> ProcedureRunStepStateResponse:
    return ProcedureRunStepStateResponse(
        id=state.id,
        run_id=state.run_id,
        step_key=state.step_key,
        payload=state.payload,
        committed_at=state.committed_at,
    )


@router.post('/procedures', response_model=ProcedureResponse, status_code=status.HTTP_201_CREATED)
def create_procedure(payload: ProcedureCreateRequest, db: Session = Depends(get_db)) -> ProcedureResponse:
    if payload.id:
        existing = db.get(models.Procedure, payload.id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Procedure already exists')

    procedure = models.Procedure(
        id=payload.id if payload.id else None,
        name=payload.name,
        description=payload.description,
    )
    db.add(procedure)
    db.flush()

    for index, step_payload in enumerate(payload.steps):
        position = step_payload.position if step_payload.position is not None else index
        step = models.ProcedureStep(
            procedure_id=procedure.id,
            key=step_payload.key,
            title=step_payload.title,
            prompt=step_payload.prompt,
            slots=step_payload.slots,
            position=position,
        )
        db.add(step)

    db.commit()
    db.refresh(procedure)
    procedure_response = _to_procedure_response(procedure)
    audit.procedure_created(db, actor=payload.actor, procedure=_serialise_procedure(procedure))
    return procedure_response


@router.get('/procedures', response_model=List[ProcedureResponse])
def list_procedures(db: Session = Depends(get_db)) -> List[ProcedureResponse]:
    procedures = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .order_by(models.Procedure.name)
        .all()
    )
    return [_to_procedure_response(procedure) for procedure in procedures]


@router.get('/procedures/{procedure_id}', response_model=ProcedureResponse)
def get_procedure(procedure_id: str, db: Session = Depends(get_db)) -> ProcedureResponse:
    procedure = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .filter(models.Procedure.id == procedure_id)
        .one_or_none()
    )
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Procedure not found')
    return _to_procedure_response(procedure)


@router.post('/runs', response_model=ProcedureRunResponse, status_code=status.HTTP_201_CREATED)
def create_run(payload: ProcedureRunCreateRequest, db: Session = Depends(get_db)) -> ProcedureRunResponse:
    procedure = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .filter(models.Procedure.id == payload.procedure_id)
        .one_or_none()
    )
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Procedure not found')

    user_id = payload.user_id or payload.actor
    run = models.ProcedureRun(
        procedure_id=procedure.id,
        user_id=user_id,
        state='in_progress',
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    audit.run_created(db, actor=payload.actor, run=_serialise_run(run))
    return _to_run_response(run)


@router.get('/runs/{run_id}', response_model=ProcedureRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)) -> ProcedureRunResponse:
    run = db.get(models.ProcedureRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Run not found')
    return _to_run_response(run)


@router.post('/runs/{run_id}/steps/{step_key}/commit', response_model=StepCommitResponse)
def commit_step(
    run_id: str,
    step_key: str,
    payload: StepCommitRequest,
    db: Session = Depends(get_db),
) -> StepCommitResponse:
    run = (
        db.query(models.ProcedureRun)
        .options(selectinload(models.ProcedureRun.procedure).selectinload(models.Procedure.steps))
        .filter(models.ProcedureRun.id == run_id)
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Run not found')
    if run.state not in {'in_progress', 'pending'}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Run is not active')

    procedure_steps = {step.key: step for step in run.procedure.steps}
    if step_key not in procedure_steps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Step not found in procedure')

    existing_state = (
        db.query(models.ProcedureRunStepState)
        .filter(
            models.ProcedureRunStepState.run_id == run.id,
            models.ProcedureRunStepState.step_key == step_key,
        )
        .one_or_none()
    )

    before_payload: Optional[Dict[str, Any]] = None
    if existing_state is not None:
        before_payload = _serialise_step_state(existing_state)
        existing_state.payload = payload.payload
        existing_state.committed_at = datetime.utcnow()
        state = existing_state
    else:
        state = models.ProcedureRunStepState(
            run_id=run.id,
            step_key=step_key,
            payload=payload.payload,
        )
        db.add(state)

    db.flush()
    db.refresh(state)

    after_payload = _serialise_step_state(state)
    audit.step_committed(
        db,
        actor=payload.actor,
        run_id=run.id,
        step_key=step_key,
        before=before_payload,
        after=after_payload,
    )

    # Update the run state if the final step has been committed.
    ordered_keys = [step.key for step in _ordered_steps(run.procedure)]
    if step_key == ordered_keys[-1] and run.state != 'completed':
        before_run = _serialise_run(run)
        run.state = 'completed'
        run.closed_at = datetime.utcnow()
        db.flush()
        db.refresh(run)
        audit.run_updated(db, actor=payload.actor, run_id=run.id, before=before_run, after=_serialise_run(run))

    db.commit()
    return StepCommitResponse(run=_to_run_response(run), step_state=_to_step_state_response(state))


@router.get('/audit-events', response_model=List[AuditEventResponse])
def list_audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[AuditEventResponse]:
    query = db.query(models.AuditEvent)
    if entity_type:
        query = query.filter(models.AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(models.AuditEvent.entity_id == entity_id)

    events = query.order_by(models.AuditEvent.occurred_at.asc()).all()
    return [
        AuditEventResponse(
            id=event.id,
            actor=event.actor,
            occurred_at=event.occurred_at,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            payload_diff=event.payload_diff,
        )
        for event in events
    ]
