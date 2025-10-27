from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _generate_uuid() -> str:
    """Generate a random UUID stored as string.

    Using a helper keeps the declarative models concise while ensuring
    consistency across tables relying on UUID primary keys.
    """

    return str(uuid.uuid4())


class Procedure(Base):
    """Top-level definition of an executable procedure."""

    __tablename__ = "procedures"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_payload: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        doc="Informations additionnelles (version, domaine métier, etc.).",
    )

    steps: Mapped[List["ProcedureStep"]] = relationship(
        "ProcedureStep",
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="ProcedureStep.position",
    )


class ProcedureStep(Base):
    """Ordered step composing a procedure."""

    __tablename__ = "procedure_steps"
    __table_args__ = (
        UniqueConstraint("procedure_id", "key", name="uq_procedure_step_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    procedure_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(default=0, nullable=False)
    metadata_payload: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        doc="Données complémentaires (conditions, pièces jointes, etc.).",
    )

    procedure: Mapped[Procedure] = relationship("Procedure", back_populates="steps")
    slots: Mapped[List["ProcedureSlot"]] = relationship(
        "ProcedureSlot",
        back_populates="step",
        cascade="all, delete-orphan",
        order_by="ProcedureSlot.position",
    )
    checklist_items: Mapped[List["ProcedureStepChecklistItem"]] = relationship(
        "ProcedureStepChecklistItem",
        back_populates="step",
        cascade="all, delete-orphan",
        order_by="ProcedureStepChecklistItem.position",
    )


class ProcedureSlot(Base):
    """Definition of a dynamic input required to complete a procedure step."""

    __tablename__ = "procedure_slots"
    __table_args__ = (
        UniqueConstraint("step_id", "name", name="uq_procedure_slot_name"),
        Index("ix_procedure_slots_step_id", "step_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    step_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_steps.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Identifiant technique du slot utilisé dans les payloads API.",
    )
    label: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Libellé lisible exposé dans l'interface utilisateur.",
    )
    slot_type: Mapped[str] = mapped_column(
        "type",
        String(50),
        nullable=False,
        doc="Type logique du slot (string, number, enum, email, phone, etc.).",
    )
    required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Impose que le slot soit renseigné pour finaliser l'étape.",
    )
    position: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        doc="Ordre d'affichage/collecte du slot dans l'étape.",
    )
    configuration: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        doc="Paramètres complémentaires (validation, masque, options, etc.).",
    )

    step: Mapped[ProcedureStep] = relationship("ProcedureStep", back_populates="slots")
    values: Mapped[List["ProcedureRunSlotValue"]] = relationship(
        "ProcedureRunSlotValue",
        back_populates="slot",
        cascade="all, delete-orphan",
    )


class ProcedureStepChecklistItem(Base):
    """Checklist item to be confirmed while completing a procedure step."""

    __tablename__ = "procedure_step_checklist_items"
    __table_args__ = (
        UniqueConstraint("step_id", "key", name="uq_procedure_step_checklist_key"),
        Index("ix_procedure_step_checklist_items_step_id", "step_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    step_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_steps.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Identifiant unique de l'item de checklist pour l'étape.",
    )
    label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Libellé lisible par un humain utilisé dans l'interface et les audits.",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Informations supplémentaires pour guider l'opérateur.",
    )
    required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Impose que l'item soit complété avant de clôturer l'étape.",
    )
    position: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        doc="Ordre d'affichage dans la checklist.",
    )

    step: Mapped[ProcedureStep] = relationship(
        "ProcedureStep",
        back_populates="checklist_items",
    )
    run_states: Mapped[List["ProcedureRunChecklistItemState"]] = relationship(
        "ProcedureRunChecklistItemState",
        back_populates="checklist_item",
        cascade="all, delete-orphan",
    )


class ProcedureRun(Base):
    """Execution instance of a procedure for a specific user."""

    __tablename__ = "procedure_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    procedure_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    procedure: Mapped[Procedure] = relationship("Procedure")
    step_states: Mapped[List["ProcedureRunStepState"]] = relationship(
        "ProcedureRunStepState",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ProcedureRunStepState.committed_at",
    )
    checklist_states: Mapped[List["ProcedureRunChecklistItemState"]] = relationship(
        "ProcedureRunChecklistItemState",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    slot_values: Mapped[List["ProcedureRunSlotValue"]] = relationship(
        "ProcedureRunSlotValue",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class ProcedureRunSlotValue(Base):
    """Value captured for a given slot while executing a procedure run."""

    __tablename__ = "procedure_run_slot_values"
    __table_args__ = (
        UniqueConstraint("run_id", "slot_id", name="uq_procedure_run_slot_value"),
        Index("ix_procedure_run_slot_values_run_id", "run_id"),
        Index("ix_procedure_run_slot_values_slot_id", "slot_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_runs.id", ondelete="CASCADE"), nullable=False
    )
    slot_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_slots.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[Any] = mapped_column(
        JSON,
        nullable=True,
        doc="Valeur saisie par l'utilisateur (avant validation métier avancée).",
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc="Horodatage de la dernière mise à jour de la valeur du slot.",
    )

    run: Mapped[ProcedureRun] = relationship("ProcedureRun", back_populates="slot_values")
    slot: Mapped[ProcedureSlot] = relationship("ProcedureSlot", back_populates="values")


class ProcedureRunChecklistItemState(Base):
    """Completion status of a checklist item within a specific run."""

    __tablename__ = "procedure_run_checklist_item_states"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "checklist_item_id",
            name="uq_procedure_run_checklist_item_state",
        ),
        Index(
            "ix_procedure_run_checklist_item_states_run_id",
            "run_id",
        ),
        Index(
            "ix_procedure_run_checklist_item_states_item_id",
            "checklist_item_id",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_runs.id", ondelete="CASCADE"), nullable=False
    )
    checklist_item_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("procedure_step_checklist_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="État booléen exposé côté API pour suivre la progression.",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        doc="Horodatage optionnel de complétion de l'item.",
    )

    run: Mapped[ProcedureRun] = relationship(
        "ProcedureRun", back_populates="checklist_states"
    )
    checklist_item: Mapped[ProcedureStepChecklistItem] = relationship(
        "ProcedureStepChecklistItem", back_populates="run_states"
    )


class ProcedureRunStepState(Base):
    """Snapshot of a step payload committed during a run."""

    __tablename__ = "procedure_run_step_states"
    __table_args__ = (
        UniqueConstraint("run_id", "step_key", name="uq_run_step"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("procedure_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )
    committed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    run: Mapped[ProcedureRun] = relationship("ProcedureRun", back_populates="step_states")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_actor", "actor"),
        Index("ix_audit_events_occurred_at", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_diff: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )


class WebRTCSession(Base):
    """Persisted WebRTC signaling session state."""

    __tablename__ = "webrtc_sessions"
    __table_args__ = (
        Index("ix_webrtc_sessions_client", "client_id"),
        Index("ix_webrtc_sessions_status", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_uuid)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    responder_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="awaiting_answer")
    offer_sdp: Mapped[str] = mapped_column(Text, nullable=False)
    answer_sdp: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_metadata: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    responder_metadata: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    ice_candidates: Mapped[List[Dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

