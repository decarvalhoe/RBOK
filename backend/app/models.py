from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class Procedure(Base):
    __tablename__ = "procedures"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    steps: Mapped[List["ProcedureStep"]] = relationship(
        "ProcedureStep",
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="ProcedureStep.position",
    )


class ProcedureStep(Base):
    __tablename__ = "procedure_steps"
    __table_args__ = (UniqueConstraint("procedure_id", "key", name="uq_procedure_step_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    procedure_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    slots: Mapped[List[dict]] = mapped_column(JSON, nullable=False, default=list)
    position: Mapped[int] = mapped_column(default=0, nullable=False)

    procedure: Mapped[Procedure] = relationship("Procedure", back_populates="steps")


class ProcedureRun(Base):
    __tablename__ = "procedure_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    procedure_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    procedure: Mapped[Procedure] = relationship("Procedure")


class ProcedureRunStepState(Base):
    __tablename__ = "procedure_run_step_states"
    __table_args__ = (UniqueConstraint("run_id", "step_key", name="uq_run_step"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("procedure_runs.id", ondelete="CASCADE"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[Dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    committed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    run: Mapped[ProcedureRun] = relationship("ProcedureRun")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_actor", "actor"),
        Index("ix_audit_events_occurred_at", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_diff: Mapped[Dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
