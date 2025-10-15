"""Domain services to manage procedure definitions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session, selectinload

from .. import models
from . import audit

ProcedurePayload = Dict[str, Any]


class ProcedureDefinitionError(Exception):
    """Raised when a procedure definition payload is invalid."""

    def __init__(self, message: str, *, issues: Optional[List[Dict[str, str]]] = None) -> None:
        super().__init__(message)
        self.issues = issues or []


class ProcedureService:
    """Provide CRUD-style helpers for :class:`~backend.app.models.Procedure`."""

    def __init__(self, db: Session):
        self._db = db

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def list_procedures(self) -> List[models.Procedure]:
        """Return all procedures ordered by their configured position."""

        return (
            self._db.query(models.Procedure)
            .options(
                selectinload(models.Procedure.steps).selectinload(
                    models.ProcedureStep.slots
                ),
                selectinload(models.Procedure.steps).selectinload(
                    models.ProcedureStep.checklist_items
                ),
            )
            .order_by(models.Procedure.name.asc())
            .all()
        )

    def get_procedure(self, procedure_id: str) -> Optional[models.Procedure]:
        """Return a single procedure with its steps eagerly loaded."""

        return (
            self._db.query(models.Procedure)
            .options(
                selectinload(models.Procedure.steps).selectinload(
                    models.ProcedureStep.slots
                ),
                selectinload(models.Procedure.steps).selectinload(
                    models.ProcedureStep.checklist_items
                ),
            )
            .filter(models.Procedure.id == procedure_id)
            .one_or_none()
        )

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------
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

        _ensure_unique_components(steps_payload)

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
            self._apply_steps(procedure, steps_payload)

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

        self._apply_steps(procedure, steps_payload)

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
                _serialise_step(step)
                for step in sorted(procedure.steps, key=lambda item: item.position)
            ],
        }

    def _apply_steps(
        self, procedure: models.Procedure, steps_payload: Iterable[Dict[str, Any]]
    ) -> None:
        procedure.steps.clear()
        for index, step_payload in enumerate(steps_payload):
            procedure.steps.append(_build_step(step_payload, index))


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


def _ensure_unique_components(steps: Iterable[Dict[str, Any]]) -> None:
    issues: List[Dict[str, str]] = []
    seen_steps: Dict[str, int] = {}

    for step_index, step in enumerate(steps):
        key = step.get("key")
        if isinstance(key, str):
            if key in seen_steps:
                issues.append(
                    {
                        "field": f"steps[{step_index}].key",
                        "message": f"Duplicate step key '{key}' detected.",
                    }
                )
            else:
                seen_steps[key] = step_index

        slot_names: Dict[str, int] = {}
        for slot_index, slot in enumerate(step.get("slots") or []):
            name = slot.get("name")
            if not isinstance(name, str):
                continue
            if name in slot_names:
                issues.append(
                    {
                        "field": f"steps[{step_index}].slots[{slot_index}].name",
                        "message": f"Duplicate slot name '{name}' detected in step '{key}'.",
                    }
                )
            else:
                slot_names[name] = slot_index

        checklist_keys: Dict[str, int] = {}
        for item_index, item in enumerate(step.get("checklists") or []):
            checklist_key = item.get("key")
            if not isinstance(checklist_key, str):
                continue
            if checklist_key in checklist_keys:
                issues.append(
                    {
                        "field": f"steps[{step_index}].checklists[{item_index}].key",
                        "message": f"Duplicate checklist key '{checklist_key}' detected in step '{key}'.",
                    }
                )
            else:
                checklist_keys[checklist_key] = item_index

    if issues:
        raise ProcedureDefinitionError(
            "Duplicate keys detected in procedure definition.", issues=issues
        )


def _build_step(payload: Dict[str, Any], default_position: int) -> models.ProcedureStep:
    slots = _ensure_list_of_dicts(payload.get("slots"))
    checklists = _ensure_list_of_dicts(payload.get("checklists"))
    metadata = _ensure_dict(payload.get("metadata"))

    position = payload.get("position")
    if not isinstance(position, int):
        position = default_position

    step = models.ProcedureStep(
        key=payload["key"],
        title=payload["title"],
        prompt=payload.get("prompt") or "",
        metadata_payload=metadata,
        position=position,
    )

    for slot_index, slot_payload in enumerate(slots):
        step.slots.append(_build_slot(slot_payload, slot_index))

    for checklist_index, checklist_payload in enumerate(checklists):
        step.checklist_items.append(
            _build_checklist_item(checklist_payload, checklist_index)
        )

    return step


def _build_slot(payload: Dict[str, Any], default_position: int) -> models.ProcedureSlot:
    configuration = _ensure_dict(payload.get("metadata"))

    position = payload.get("position")
    if not isinstance(position, int):
        position = default_position

    return models.ProcedureSlot(
        name=payload["name"],
        label=payload.get("label"),
        slot_type=payload.get("type", "string"),
        required=payload.get("required", True),
        position=position,
        configuration=configuration,
    )


def _build_checklist_item(
    payload: Dict[str, Any], default_position: int
) -> models.ProcedureStepChecklistItem:
    position = payload.get("position")
    if not isinstance(position, int):
        position = default_position

    return models.ProcedureStepChecklistItem(
        key=payload["key"],
        label=payload.get("label", payload["key"]),
        description=payload.get("description"),
        required=payload.get("required", False),
        position=position,
    )


def _serialise_step(step: models.ProcedureStep) -> Dict[str, Any]:
    return {
        "id": step.id,
        "key": step.key,
        "title": step.title,
        "prompt": step.prompt,
        "position": step.position,
        "metadata": deepcopy(step.metadata_payload or {}),
        "slots": [
            {
                "id": slot.id,
                "name": slot.name,
                "label": slot.label,
                "type": slot.slot_type,
                "required": slot.required,
                "position": slot.position,
                "metadata": deepcopy(slot.configuration or {}),
            }
            for slot in sorted(step.slots, key=lambda item: item.position)
        ],
        "checklists": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
                "description": item.description,
                "required": item.required,
                "position": item.position,
            }
            for item in sorted(step.checklist_items, key=lambda entry: entry.position)
        ],
    }


__all__ = ["ProcedureService", "ProcedureDefinitionError"]
