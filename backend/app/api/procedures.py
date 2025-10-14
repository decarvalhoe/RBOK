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
