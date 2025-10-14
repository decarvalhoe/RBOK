"""Serialization helpers for ORM models exposed via the API."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from ..models import (
    Procedure,
    ProcedureRun,
    ProcedureRunStepState,
    ProcedureSlot,
    ProcedureStep,
    ProcedureStepChecklistItem,
)


def _serialize_slot(slot: ProcedureSlot) -> Dict[str, Any]:
    """Convert a :class:`ProcedureSlot` into a plain dictionary."""

    metadata = deepcopy(getattr(slot, "configuration", {}) or {})
    return {
        "name": slot.name,
        "type": slot.slot_type,
        "required": bool(slot.required),
        "label": slot.label,
        "description": metadata.get("description"),
        "validate": metadata.get("validate"),
        "mask": metadata.get("mask"),
        "options": metadata.get("options"),
        "position": slot.position,
        "metadata": metadata,
        "id": slot.id,
    }


def _serialize_checklist_item(item: ProcedureStepChecklistItem) -> Dict[str, Any]:
    """Convert a :class:`ProcedureStepChecklistItem` into a plain dictionary."""

    return {
        "key": item.key,
        "label": item.label,
        "description": item.description,
        "required": bool(item.required),
        "default_state": None,
        "position": item.position,
        "metadata": {},
        "id": item.id,
    }


def _serialize_step(step: ProcedureStep) -> Dict[str, Any]:
    """Convert a :class:`ProcedureStep` into a plain dictionary."""

    return {
        "id": step.id,
        "key": step.key,
        "title": step.title,
        "prompt": step.prompt or None,
        "position": step.position,
        "metadata": deepcopy(getattr(step, "metadata_payload", {}) or {}),
        "slots": [_serialize_slot(slot) for slot in sorted(step.slots, key=lambda item: item.position)],
        "checklists": [
            _serialize_checklist_item(item)
            for item in sorted(step.checklist_items, key=lambda entry: entry.position)
        ],
    }


def serialize_procedure(procedure: Procedure) -> Dict[str, Any]:
    return {
        "id": procedure.id,
        "name": procedure.name,
        "description": procedure.description,
        "metadata": deepcopy(getattr(procedure, "metadata_payload", {}) or {}),
        "steps": [_serialize_step(step) for step in sorted(procedure.steps, key=lambda item: item.position)],
    }


def serialize_run(
    run: ProcedureRun,
    step_states: Iterable[ProcedureRunStepState],
) -> Dict[str, Any]:
    states: List[Dict[str, Any]] = []
    for state in step_states:
        states.append(
            {
                "id": state.id,
                "step_key": state.step_key,
                "payload": dict(getattr(state, "payload", {}) or {}),
                "committed_at": state.committed_at.isoformat(),
            }
        )

    procedure_payload = serialize_procedure(run.procedure) if run.procedure else None

    return {
        "id": run.id,
        "procedure_id": run.procedure_id,
        "user_id": run.user_id,
        "state": run.state,
        "created_at": run.created_at.isoformat(),
        "closed_at": run.closed_at.isoformat() if run.closed_at else None,
        "procedure": procedure_payload,
        "step_states": states,
    }


__all__ = ["serialize_procedure", "serialize_run"]
