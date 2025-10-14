"""Serialization helpers for ORM models exposed via the API."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..models import Procedure, ProcedureRun, ProcedureRunStepState


def serialize_procedure(procedure: Procedure) -> Dict[str, Any]:
    return {
        "id": procedure.id,
        "name": procedure.name,
        "description": procedure.description,
        "steps": [
            {
                "id": step.id,
                "key": step.key,
                "title": step.title,
                "prompt": step.prompt,
                "slots": step.slots,
                "position": step.position,
            }
            for step in sorted(procedure.steps, key=lambda item: item.position)
        ],
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
                "payload": state.payload,
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
