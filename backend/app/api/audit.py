"""HTTP endpoints exposing stored audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import User, get_current_user
from ..database import get_db
from ..models import AuditEvent


class AuditEventModel(BaseModel):
    """Public representation of a persisted audit event."""

    id: str
    actor: str
    action: str
    entity_type: str
    entity_id: str
    occurred_at: datetime
    payload_diff: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=List[AuditEventModel])
async def list_audit_events(
    *,
    entity_type: str = Query(..., min_length=1, max_length=255),
    entity_id: str = Query(..., min_length=1, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AuditEventModel]:
    """Return audit events recorded for the requested entity."""

    statement = (
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == entity_id,
        )
        .order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
    )
    events = db.execute(statement).scalars().all()
    return [AuditEventModel.model_validate(event) for event in events]


__all__ = ["router"]

