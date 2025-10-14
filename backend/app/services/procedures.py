"""Domain services to manage procedure definitions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session, selectinload

from .. import models
from . import audit

ProcedurePayload = Dict[str, Any]


class DuplicateProcedureComponentError(ValueError):
    """Raised when procedure components use duplicate identifiers."""

    def __init__(self, message: str):
        super().__init__(message)


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


def _ensure_unique_components(steps_payload: Iterable[Dict[str, Any]]) -> None:
    step_keys = [step.get("key") for step in steps_payload if step.get("key")]
    duplicate_steps = _find_duplicates(step_keys)
    if duplicate_steps:
        raise DuplicateProcedureComponentError(
            f"Duplicate step key(s): {', '.join(sorted(duplicate_steps))}"
        )

    for step in steps_payload:
        step_key = step.get("key", "<unknown>")

        slots = _ensure_list_of_dicts(step.get("slots"))
        duplicate_slots = _find_duplicates(slot.get("name") for slot in slots if slot.get("name"))
        if duplicate_slots:
            raise DuplicateProcedureComponentError(
                "Duplicate slot name(s) in step "
                f"'{step_key}': {', '.join(sorted(duplicate_slots))}"
            )

        checklists = _ensure_list_of_dicts(step.get("checklists"))
        duplicate_checklists = _find_duplicates(
            item.get("key") for item in checklists if item.get("key")
        )
        if duplicate_checklists:
            raise DuplicateProcedureComponentError(
                "Duplicate checklist key(s) in step "
                f"'{step_key}': {', '.join(sorted(duplicate_checklists))}"
            )


def _find_duplicates(values: Iterable[Optional[str]]) -> List[str]:
    seen = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        else:
            seen.add(value)
    return duplicates


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


__all__ = ["DuplicateProcedureComponentError", "ProcedureService"]
