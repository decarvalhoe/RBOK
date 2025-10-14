"""Business services orchestrating procedure run lifecycle."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models
from . import audit


class ProcedureNotFoundError(RuntimeError):
    """Raised when attempting to start a run for a missing procedure."""

    def __init__(self, procedure_id: str) -> None:
        super().__init__(f"Procedure '{procedure_id}' not found")
        self.procedure_id = procedure_id


class ProcedureRunNotFoundError(RuntimeError):
    """Raised when a procedure run cannot be located."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run '{run_id}' not found")
        self.run_id = run_id


class InvalidTransitionError(RuntimeError):
    """Raised when a state transition is not permitted by the FSM."""

    def __init__(self, *, run_id: str, message: str) -> None:
        super().__init__(message)
        self.run_id = run_id


class SlotValidationError(ValueError):
    """Raised when collected slots do not match their definitions."""

    def __init__(self, issues: List[Dict[str, Any]]) -> None:
        super().__init__("Slot validation failed")
        self.issues = issues


class ChecklistValidationError(ValueError):
    """Raised when checklist submission is malformed."""

    def __init__(self, issues: List[Dict[str, Any]]) -> None:
        super().__init__("Checklist validation failed")
        self.issues = issues


@dataclass
class RunSnapshot:
    """In-memory snapshot of a run state and its committed steps."""

    run: models.ProcedureRun
    step_states: Dict[str, models.ProcedureRunStepState]


_SLOT_TYPE_MAPPING: Dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _mask_to_regex(mask: str) -> str:
    """Convert a simple ``X`` mask into a regular expression pattern."""

    escaped: List[str] = []
    for character in mask:
        if character == "X":
            escaped.append(r"\d")
        else:
            escaped.append(re.escape(character))
    return "^" + "".join(escaped) + "$"


class ProcedureRunService:
    """High-level orchestration of the procedure run lifecycle."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start_run(
        self, *, procedure_id: str, user_id: str, actor: Optional[str] = None
    ) -> models.ProcedureRun:
        """Create a new run for the given procedure."""

        procedure = self._get_procedure(procedure_id)
        if procedure is None:
            raise ProcedureNotFoundError(procedure_id)

        run = models.ProcedureRun(
            procedure_id=procedure.id,
            user_id=user_id,
            state="pending",
        )
        self._db.add(run)
        self._db.flush()

        audit_actor = actor or user_id
        audit.run_created(
            self._db,
            actor=audit_actor,
            run=self._serialise_run(run),
        )
        self._db.refresh(run)
        return run

    def get_snapshot(self, run_id: str) -> RunSnapshot:
        """Return a hydrated snapshot of the run and its step states."""

        run = self._load_run(run_id)
        states = {state.step_key: state for state in run.step_states}
        return RunSnapshot(run=run, step_states=states)

    def commit_step(
        self,
        *,
        run_id: str,
        step_key: str,
        slots: Dict[str, Any],
        checklist: Iterable[Dict[str, Any]],
        actor: Optional[str] = None,
    ) -> RunSnapshot:
        """Commit a step payload and advance the FSM when appropriate."""

        snapshot = self.get_snapshot(run_id)
        run = snapshot.run

        step = self._find_step(run, step_key)
        if step is None:
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Step '{step_key}' does not exist on procedure",
            )

        if step_key in snapshot.step_states:
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Step '{step_key}' already committed",
            )

        self._ensure_previous_steps_committed(run, snapshot.step_states, step_key)

        self._validate_slots(step, slots)
        raw_checklist = list(checklist)
        self._validate_checklist(step, raw_checklist)
        checklist_states = self._build_checklist_states(step, raw_checklist)

        payload = {
            "slots": self._serialise_slots(step, slots),
            "checklist": self._serialise_checklist(checklist_states),
        }
        step_state = models.ProcedureRunStepState(
            run_id=run.id,
            step_key=step.key,
            payload=payload,
        )
        self._db.add(step_state)

        self._persist_slot_values(run, step, slots)
        self._persist_checklist_states(run, checklist_states)

        previous_state = run.state
        previous_closed_at = run.closed_at

        if run.state == "pending":
            run.state = "in_progress"

        expected_total = len(run.procedure.steps)
        committed_total = len(snapshot.step_states) + 1
        if committed_total >= expected_total:
            run.state = "completed"
            run.closed_at = datetime.utcnow()

        self._db.flush()

        resolved_actor = actor or run.user_id
        audit.step_committed(
            self._db,
            actor=resolved_actor,
            run_id=run.id,
            step_key=step.key,
            before=None,
            after={
                "payload": payload,
                "committed_at": step_state.committed_at.isoformat(),
            },
        )

        if run.state != previous_state or run.closed_at != previous_closed_at:
            audit.run_updated(
                self._db,
                actor=resolved_actor,
                run_id=run.id,
                before={
                    "state": previous_state,
                    "closed_at": previous_closed_at.isoformat()
                    if previous_closed_at
                    else None,
                },
                after={
                    "state": run.state,
                    "closed_at": run.closed_at.isoformat() if run.closed_at else None,
                },
            )

        self._db.refresh(run)
        self._db.refresh(step_state)
        snapshot.step_states[step_key] = step_state
        return RunSnapshot(run=run, step_states=snapshot.step_states)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_procedure(self, procedure_id: str) -> Optional[models.Procedure]:
        stmt = select(models.Procedure).where(models.Procedure.id == procedure_id)
        return self._db.execute(stmt).scalars().first()

    def _load_run(self, run_id: str) -> models.ProcedureRun:
        stmt = (
            select(models.ProcedureRun)
            .where(models.ProcedureRun.id == run_id)
            .options(
                selectinload(models.ProcedureRun.procedure).selectinload(
                    models.Procedure.steps
                ).selectinload(models.ProcedureStep.slots),
                selectinload(models.ProcedureRun.procedure).selectinload(
                    models.Procedure.steps
                ).selectinload(models.ProcedureStep.checklist_items),
                selectinload(models.ProcedureRun.step_states),
                selectinload(models.ProcedureRun.checklist_states).selectinload(
                    models.ProcedureRunChecklistItemState.checklist_item
                ),
                selectinload(models.ProcedureRun.slot_values).selectinload(
                    models.ProcedureRunSlotValue.slot
                ),
            )
        )
        run = self._db.execute(stmt).scalars().first()
        if run is None:
            raise ProcedureRunNotFoundError(run_id)
        return run

    def _find_step(
        self, run: models.ProcedureRun, step_key: str
    ) -> Optional[models.ProcedureStep]:
        for step in sorted(run.procedure.steps, key=lambda item: item.position):
            if step.key == step_key:
                return step
        return None

    def _ensure_previous_steps_committed(
        self,
        run: models.ProcedureRun,
        step_states: Dict[str, models.ProcedureRunStepState],
        step_key: str,
    ) -> None:
        ordered_steps = sorted(run.procedure.steps, key=lambda item: item.position)
        for step in ordered_steps:
            if step.key == step_key:
                break
            if step.key not in step_states:
                raise InvalidTransitionError(
                    run_id=run.id,
                    message=f"Step '{step.key}' must be committed before '{step_key}'",
                )

    def _validate_slots(self, step: models.ProcedureStep, slots: Dict[str, Any]) -> None:
        issues: List[Dict[str, Any]] = []
        definitions = {slot.name: slot for slot in step.slots}

        for slot_name, definition in definitions.items():
            if definition.required and slot_name not in slots:
                issues.append({"slot": slot_name, "reason": "missing_required_value"})

        for provided in slots.keys():
            if provided not in definitions:
                issues.append({"slot": provided, "reason": "unknown_slot"})

        for name, value in slots.items():
            definition = definitions.get(name)
            if definition is None:
                continue
            expected_type = definition.slot_type
            if expected_type and expected_type in _SLOT_TYPE_MAPPING:
                python_type = _SLOT_TYPE_MAPPING[expected_type]
                if not isinstance(value, python_type):
                    issues.append(
                        {
                            "slot": name,
                            "reason": "invalid_type",
                            "expected": expected_type,
                        }
                    )
                    continue

            mask = (definition.configuration or {}).get("mask")
            if mask and isinstance(value, str):
                pattern = _mask_to_regex(mask)
                if re.fullmatch(pattern, value) is None:
                    issues.append(
                        {
                            "slot": name,
                            "reason": "mask_mismatch",
                            "mask": mask,
                        }
                    )
            elif mask and not isinstance(value, str):
                issues.append(
                    {
                        "slot": name,
                        "reason": "mask_mismatch",
                        "mask": mask,
                    }
                )

        if issues:
            raise SlotValidationError(issues)

    def _validate_checklist(
        self, step: models.ProcedureStep, checklist: List[Dict[str, Any]]
    ) -> None:
        issues: List[Dict[str, Any]] = []
        definitions = {item.key: item for item in step.checklist_items}
        seen_keys: set[str] = set()

        for index, item in enumerate(checklist):
            if not isinstance(item, dict):
                issues.append({"index": index, "reason": "invalid_item"})
                continue

            key = item.get("key")
            if not key or not isinstance(key, str):
                issues.append({"index": index, "reason": "missing_key"})
                continue

            if key in seen_keys:
                issues.append({"index": index, "reason": "duplicate_key", "key": key})
            seen_keys.add(key)

            definition = definitions.get(key)
            if definition is None:
                issues.append({"index": index, "reason": "unknown_checklist_item", "key": key})
                continue

            completed = item.get("completed")
            if not isinstance(completed, bool):
                issues.append({"index": index, "reason": "invalid_completed_flag", "key": key})
                continue

            if definition.required and not completed:
                issues.append({"index": index, "reason": "required_not_completed", "key": key})

        for required_key, definition in definitions.items():
            if definition.required and required_key not in seen_keys:
                issues.append({"reason": "missing_required_item", "key": required_key})

        if issues:
            raise ChecklistValidationError(issues)

    def _build_checklist_states(
        self, step: models.ProcedureStep, checklist: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        submissions = {item["key"]: item for item in checklist if "key" in item}
        states: List[Dict[str, Any]] = []
        for item in step.checklist_items:
            submitted = submissions.get(item.key, {})
            completed = bool(submitted.get("completed", False))
            completed_at = self._normalise_completed_at(submitted.get("completed_at"))
            if not completed:
                completed_at = None
            states.append(
                {
                    "item": item,
                    "completed": completed,
                    "completed_at": completed_at,
                }
            )
        return states

    def _serialise_slots(
        self, step: models.ProcedureStep, slots: Dict[str, Any]
    ) -> Dict[str, Any]:
        serialised: Dict[str, Any] = {}
        for slot in step.slots:
            if slot.name in slots:
                serialised[slot.name] = slots[slot.name]
        return serialised

    def _serialise_checklist(
        self, states: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        serialised: List[Dict[str, Any]] = []
        for state in states:
            item: models.ProcedureStepChecklistItem = state["item"]
            serialised.append(
                {
                    "key": item.key,
                    "label": item.label,
                    "completed": state["completed"],
                    "completed_at": state["completed_at"].isoformat()
                    if state["completed_at"]
                    else None,
                }
            )
        return serialised

    def _persist_slot_values(
        self,
        run: models.ProcedureRun,
        step: models.ProcedureStep,
        slots: Dict[str, Any],
    ) -> None:
        for slot in step.slots:
            if slot.name not in slots:
                continue
            slot_value = models.ProcedureRunSlotValue(
                run_id=run.id,
                slot_id=slot.id,
                value=slots[slot.name],
            )
            self._db.add(slot_value)

    def _persist_checklist_states(
        self,
        run: models.ProcedureRun,
        states: List[Dict[str, Any]],
    ) -> None:
        for state in states:
            item: models.ProcedureStepChecklistItem = state["item"]
            checklist_state = models.ProcedureRunChecklistItemState(
                run_id=run.id,
                checklist_item_id=item.id,
                is_completed=state["completed"],
                completed_at=state["completed_at"],
            )
            self._db.add(checklist_state)

    @staticmethod
    def _normalise_completed_at(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _serialise_run(run: models.ProcedureRun) -> Dict[str, Any]:
        return {
            "id": run.id,
            "procedure_id": run.procedure_id,
            "user_id": run.user_id,
            "state": run.state,
            "created_at": run.created_at.isoformat(),
            "closed_at": run.closed_at.isoformat() if run.closed_at else None,
        }


__all__ = [
    "ProcedureRunService",
    "ProcedureNotFoundError",
    "ProcedureRunNotFoundError",
    "InvalidTransitionError",
    "SlotValidationError",
    "ChecklistValidationError",
    "RunSnapshot",
]
