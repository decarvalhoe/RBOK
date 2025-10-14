"""Procedural management endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.auth import User, require_role
from app.database import get_db

router = APIRouter(prefix="/procedures", tags=["procedures"])


class SlotDefinition(BaseModel):
    """Definition of a slot collected during a procedure step."""

    name: str
    type: str = Field(default="string")
    label: str | None = None
    required: bool = False
    options: List[str] | None = None


class ChecklistItemDefinition(BaseModel):
    """Definition of a checklist item for a procedure step."""

    name: str
    label: str | None = None
    required: bool = False


class ProcedureStepPayload(BaseModel):
    """Payload used to create a procedure step."""

    key: str
    title: str
    prompt: str
    slots: List[SlotDefinition] = Field(default_factory=list)
    checklist: List[ChecklistItemDefinition] = Field(default_factory=list)


class ProcedureCreate(BaseModel):
    name: str
    description: str
    steps: List[ProcedureStepPayload]


class ProcedureStepResponse(ProcedureStepPayload):
    id: str
    position: int

    model_config = ConfigDict(from_attributes=True)


class ProcedureResponse(BaseModel):
    id: str
    name: str
    description: str
    steps: List[ProcedureStepResponse]

    model_config = ConfigDict(from_attributes=True)


class ProcedureSummary(BaseModel):
    id: str
    name: str
    description: str

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=ProcedureResponse, status_code=status.HTTP_201_CREATED)
def create_procedure(
    payload: ProcedureCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> ProcedureResponse:
    procedure = models.Procedure(name=payload.name, description=payload.description)
    for position, step_payload in enumerate(payload.steps):
        step = models.ProcedureStep(
            key=step_payload.key,
            title=step_payload.title,
            prompt=step_payload.prompt,
            slots=[slot.model_dump() for slot in step_payload.slots],
            checklist=[item.model_dump() for item in step_payload.checklist],
            position=position,
        )
        procedure.steps.append(step)

    db.add(procedure)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Duplicate step key or invalid payload") from exc
    db.refresh(procedure)
    return ProcedureResponse.model_validate(procedure)


@router.get("", response_model=List[ProcedureSummary])
def list_procedures(db: Session = Depends(get_db)) -> List[ProcedureSummary]:
    procedures = db.query(models.Procedure).order_by(models.Procedure.name).all()
    return [ProcedureSummary.model_validate(proc) for proc in procedures]


@router.get("/{procedure_id}", response_model=ProcedureResponse)
def get_procedure(procedure_id: str, db: Session = Depends(get_db)) -> ProcedureResponse:
    procedure = db.get(models.Procedure, procedure_id)
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")
    return ProcedureResponse.model_validate(procedure)


__all__ = [
    "router",
    "ProcedureCreate",
    "ProcedureResponse",
]
