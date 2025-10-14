from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict, MutableList

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
    checklist_items: Mapped[List["ProcedureStepChecklistItem"]] = relationship(
        "ProcedureStepChecklistItem",
        back_populates="step",
        cascade="all, delete-orphan",
        order_by="ProcedureStepChecklistItem.position",
    )


class ProcedureStepChecklistItem(Base):
    __tablename__ = "procedure_step_checklist_items"
    __table_args__ = (
        UniqueConstraint("step_id", "key", name="uq_step_checklist_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    step_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_steps.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(default=0, nullable=False)

    step: Mapped[ProcedureStep] = relationship("ProcedureStep", back_populates="checklist_items")
    run_statuses: Mapped[List["ProcedureRunChecklistStatus"]] = relationship(
        "ProcedureRunChecklistStatus",
        back_populates="checklist_item",
        cascade="all, delete-orphan",
    )


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
    step_states: Mapped[List["ProcedureRunStepState"]] = relationship(
        "ProcedureRunStepState",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ProcedureRunStepState.committed_at",
    )
    checklist_statuses: Mapped[List["ProcedureRunChecklistStatus"]] = relationship(
        "ProcedureRunChecklistStatus",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class ProcedureRunStepState(Base):
    __tablename__ = "procedure_run_step_states"
    __table_args__ = (UniqueConstraint("run_id", "step_key", name="uq_run_step"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("procedure_runs.id", ondelete="CASCADE"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[Dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    committed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    run: Mapped[ProcedureRun] = relationship("ProcedureRun", back_populates="step_states")


class ProcedureRunChecklistStatus(Base):
    __tablename__ = "procedure_run_checklist_statuses"
    __table_args__ = (
        UniqueConstraint("run_id", "checklist_item_id", name="uq_run_checklist_item"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_runs.id", ondelete="CASCADE"), nullable=False
    )
    checklist_item_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_step_checklist_items.id", ondelete="CASCADE"), nullable=False
    )
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    run: Mapped[ProcedureRun] = relationship("ProcedureRun", back_populates="checklist_statuses")
    checklist_item: Mapped[ProcedureStepChecklistItem] = relationship(
        "ProcedureStepChecklistItem",
        back_populates="run_statuses",
    )


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


class WebRTCSession(Base):
    """Persisted WebRTC signaling session state."""

    __tablename__ = "webrtc_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    responder_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="awaiting_answer")
    offer_sdp: Mapped[str] = mapped_column(Text, nullable=False)
    answer_sdp: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_metadata: Mapped[Dict[str, object]] = mapped_column(
        "metadata", MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    responder_metadata: Mapped[Dict[str, object]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    ice_candidates: Mapped[List[Dict[str, object]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
