from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Procedure, ProcedureStep

router = APIRouter(prefix="/procedures", tags=["procedures"])


class ProcedureChecklistItemModel(BaseModel):
    id: str
    key: str
    label: str
    description: str | None = None
    position: int

    model_config = ConfigDict(from_attributes=True)


class ProcedureStepModel(BaseModel):
    id: str
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, Any]]
    position: int
    checklist_items: List[ProcedureChecklistItemModel]

    model_config = ConfigDict(from_attributes=True)


class ProcedureModel(BaseModel):
    id: str
    name: str
    description: str
    steps: List[ProcedureStepModel]

    model_config = ConfigDict(from_attributes=True)


@router.get("/", response_model=List[ProcedureModel])
def list_procedures(db: Session = Depends(get_db)) -> List[Procedure]:
    procedures = (
        db.query(Procedure)
        .options(
            selectinload(Procedure.steps).selectinload(ProcedureStep.checklist_items)
        )
        .order_by(Procedure.name)
        .all()
    )
    return procedures


__all__ = ["router"]
