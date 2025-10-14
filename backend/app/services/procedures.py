"""Domain services for managing procedure definitions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session, selectinload

from .. import models
from . import audit

ProcedurePayload = Dict[str, Any]


class ProcedureService:
    """Provide CRUD-style helpers for :class:`~backend.app.models.Procedure`."""

    def __init__(self, db: Session):
        self._db = db

    # ---------------------------------------------------------------------
    # Query helpers
    # ---------------------------------------------------------------------
    def list_procedures(self) -> List[models.Procedure]:
        """Return all procedures ordered by their configured position."""

        return (
            self._db.query(models.Procedure)
            .options(selectinload(models.Procedure.steps))
            .order_by(models.Procedure.name.asc())
            .all()
        )

    def get_procedure(self, procedure_id: str) -> Optional[models.Procedure]:
        """Return a single procedure with its steps eagerly loaded."""

        return (
            self._db.query(models.Procedure)
            .options(selectinload(models.Procedure.steps))
            .filter(models.Procedure.id == procedure_id)
            .one_or_none()
        )

    # ---------------------------------------------------------------------
    # Mutation helpers
    # ---------------------------------------------------------------------
    def save_procedure(
        self,
        data: ProcedurePayload,
        *,
        actor: str,
    ) -> Tuple[models.Procedure, bool]:
        """Create a new procedure or update an existing one.

        Returns a tuple ``(procedure, created)`` where ``created`` indicates whether a
        new row has been inserted (``True``) or an existing procedure has been
        updated (``False``).
        """

        procedure_id = data.get("id")
        metadata = _ensure_dict(data.get("metadata"))
        steps_payload = list(data.get("steps") or [])

        if procedure_id:
            procedure = self.get_procedure(procedure_id)
        else:
            procedure = None

        if procedure is None:
            procedure = models.Procedure(
                id=procedure_id,
                name=data["name"],
                description=data.get("description") or "",
                metadata_payload=metadata,
            )
            for index, step_payload in enumerate(steps_payload):
                procedure.steps.append(_build_step(step_payload, index))

            self._db.add(procedure)
            self._db.commit()
            self._db.refresh(procedure)

            audit.procedure_created(
                self._db,
                actor=actor,
                procedure=self._serialize(procedure),
            )
            return procedure, True

        before = self._serialize(procedure)

        procedure.name = data["name"]
        procedure.description = data.get("description") or ""
        procedure.metadata_payload = metadata

        procedure.steps.clear()
        for index, step_payload in enumerate(steps_payload):
            procedure.steps.append(_build_step(step_payload, index))

        self._db.commit()
        self._db.refresh(procedure)

        audit.procedure_updated(
            self._db,
            actor=actor,
            procedure_id=procedure.id,
            before=before,
            after=self._serialize(procedure),
        )
        return procedure, False

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def _serialize(self, procedure: models.Procedure) -> ProcedurePayload:
        """Return a JSON-serialisable representation of ``procedure``."""

        return {
            "id": procedure.id,
            "name": procedure.name,
            "description": procedure.description,
            "metadata": deepcopy(procedure.metadata_payload or {}),
            "steps": [
                {
                    "id": step.id,
                    "key": step.key,
                    "title": step.title,
                    "prompt": step.prompt,
                    "position": step.position,
                    "metadata": deepcopy(step.metadata_payload or {}),
                    "slots": deepcopy(_extract_slots(step.slots)),
                    "checklists": deepcopy(list(step.checklists or [])),
                }
                for step in sorted(procedure.steps, key=lambda item: item.position)
            ],
        }


# -------------------------------------------------------------------------
# Helper utilities (module level)
# -------------------------------------------------------------------------

def _ensure_dict(value: Optional[Any]) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    raise TypeError("Expected a dictionary-compatible metadata payload")


def _ensure_list_of_dicts(value: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    if value is None:
        return []
    result: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            result.append(dict(item))
        else:
            raise TypeError("Expected items encoded as dictionaries")
    return result


def _extract_slots(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return _ensure_list_of_dicts(raw)
    if isinstance(raw, dict):
        return _ensure_list_of_dicts(raw.get("slots"))
    return []


def _build_step(payload: Dict[str, Any], default_position: int) -> models.ProcedureStep:
    slots = _ensure_list_of_dicts(payload.get("slots"))
    checklists = _ensure_list_of_dicts(payload.get("checklists"))
    metadata = _ensure_dict(payload.get("metadata"))

    position = payload.get("position")
    if not isinstance(position, int):
        position = default_position

    return models.ProcedureStep(
        key=payload["key"],
        title=payload["title"],
        prompt=payload.get("prompt") or "",
        slots=slots,
        metadata_payload=metadata,
        checklists=checklists,
        position=position,
    )


__all__ = ["ProcedureService"]
