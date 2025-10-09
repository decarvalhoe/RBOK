"""Audit trail helpers for recording domain changes."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .. import models

Payload = Dict[str, Any]


def _normalise_payload(payload: Optional[Payload]) -> Payload:
    """Ensure payloads are dictionaries suitable for diffing."""

    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    raise TypeError("Audit payloads must be dictionaries")


def compute_diff(before: Optional[Payload], after: Optional[Payload]) -> Payload:
    """Return a shallow diff between two payloads."""

    before_map = _normalise_payload(before)
    after_map = _normalise_payload(after)

    added = {k: v for k, v in after_map.items() if k not in before_map}
    removed = {k: v for k, v in before_map.items() if k not in after_map}
    changed = {}
    for key in before_map.keys() & after_map.keys():
        if before_map[key] != after_map[key]:
            changed[key] = {"from": before_map[key], "to": after_map[key]}

    return {"added": added, "removed": removed, "changed": changed}


def write_audit_event(
    db: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    before: Optional[Payload] = None,
    after: Optional[Payload] = None,
) -> models.AuditEvent:
    """Persist an audit event and return it."""

    payload_diff = compute_diff(before, after)
    event = models.AuditEvent(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_diff=payload_diff,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def procedure_created(db: Session, *, actor: str, procedure: Payload) -> models.AuditEvent:
    return write_audit_event(
        db,
        actor=actor,
        action="procedure.created",
        entity_type="procedure",
        entity_id=procedure.get("id", "unknown"),
        after=procedure,
    )


def procedure_updated(
    db: Session,
    *,
    actor: str,
    procedure_id: str,
    before: Payload,
    after: Payload,
) -> models.AuditEvent:
    return write_audit_event(
        db,
        actor=actor,
        action="procedure.updated",
        entity_type="procedure",
        entity_id=procedure_id,
        before=before,
        after=after,
    )


def run_created(db: Session, *, actor: str, run: Payload) -> models.AuditEvent:
    return write_audit_event(
        db,
        actor=actor,
        action="run.created",
        entity_type="procedure_run",
        entity_id=run.get("id", "unknown"),
        after=run,
    )


def run_updated(
    db: Session,
    *,
    actor: str,
    run_id: str,
    before: Payload,
    after: Payload,
) -> models.AuditEvent:
    return write_audit_event(
        db,
        actor=actor,
        action="run.updated",
        entity_type="procedure_run",
        entity_id=run_id,
        before=before,
        after=after,
    )


def step_committed(
    db: Session,
    *,
    actor: str,
    run_id: str,
    step_key: str,
    before: Optional[Payload],
    after: Payload,
) -> models.AuditEvent:
    return write_audit_event(
        db,
        actor=actor,
        action="run.step_committed",
        entity_type="procedure_run_step",
        entity_id=f"{run_id}:{step_key}",
        before=before,
        after=after,
    )
