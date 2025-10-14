"""REST endpoints exposing procedure definitions."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import User, require_role
from ..database import get_db
from ..models import Procedure, ProcedureStep
from ..services.procedures import ProcedureService
from .schemas.procedures import (
    ProcedureCreateRequest,
    ProcedureResponse,
    ProcedureSlot,
    ProcedureStepResponse,
    ProcedureChecklistItem,
)

router = APIRouter(prefix="/procedures", tags=["procedures"])


def _service(db: Session = Depends(get_db)) -> ProcedureService:
    return ProcedureService(db)


def _actor_from_user(user: User) -> str:
    return user.username or user.subject


def _to_response(model: Procedure) -> ProcedureResponse:
    steps = [_to_step_response(step) for step in sorted(model.steps, key=lambda s: s.position)]
    return ProcedureResponse(
        id=model.id,
        name=model.name,
        description=model.description,
        metadata=dict(model.metadata_payload or {}),
        steps=steps,
    )


def _to_step_response(step: ProcedureStep) -> ProcedureStepResponse:
    slots = [ProcedureSlot.model_validate(slot) for slot in step.slots or []]
    checklists = [
        ProcedureChecklistItem.model_validate(item) for item in step.checklists or []
    ]
    return ProcedureStepResponse(
        id=step.id,
        key=step.key,
        title=step.title,
        prompt=step.prompt or None,
        position=step.position,
        metadata=dict(step.metadata_payload or {}),
        slots=slots,
        checklists=checklists,
    )


@router.get("", response_model=List[ProcedureResponse])
async def list_procedures(service: ProcedureService = Depends(_service)) -> List[ProcedureResponse]:
    """Return all available procedure definitions."""

    return [_to_response(item) for item in service.list_procedures()]


@router.get("/{procedure_id}", response_model=ProcedureResponse)
async def get_procedure(
    procedure_id: str,
    service: ProcedureService = Depends(_service),
) -> ProcedureResponse:
    """Return the procedure identified by ``procedure_id``."""

    procedure = service.get_procedure(procedure_id)
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")
    return _to_response(procedure)


@router.post("", response_model=ProcedureResponse, status_code=status.HTTP_201_CREATED)
async def create_procedure(
    payload: ProcedureCreateRequest,
    response: Response,
    service: ProcedureService = Depends(_service),
    current_user: User = Depends(require_role("admin")),
) -> ProcedureResponse:
    """Create or update a procedure definition."""

    procedure, created = service.save_procedure(
        payload.model_dump(exclude_none=True),
        actor=_actor_from_user(current_user),
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return _to_response(procedure)
