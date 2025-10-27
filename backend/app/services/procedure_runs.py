"""Business services orchestrating procedure run lifecycle."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models
from . import audit
from .procedures.exceptions import (
    ChecklistValidationError as ProcedureChecklistValidationError,
)
from .procedures.exceptions import (
    InvalidTransitionError as ProcedureFSMInvalidTransitionError,
)
from .procedures.exceptions import (
    SlotValidationError as ProcedureSlotValidationError,
)
from .procedures.fsm import ProcedureRunState, apply_transition, can_transition
from .procedures.validators import ChecklistValidator, SlotDefinition, SlotValidator


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

        requested_step_key = step_key
        step = self._find_step(run, step_key)
        if step is None and requested_step_key in {"", None, "step"}:
            fallback = self._next_pending_step(run, snapshot.step_states)
            if fallback is not None:
                step = fallback
                step_key = fallback.key
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

        self._ensure_run_active(run)

        self._ensure_previous_steps_committed(run, snapshot.step_states, step_key)

        cleaned_slots = self._validate_slots(step, slots)
        raw_checklist = list(checklist)
        cleaned_checklist = self._validate_checklist(step, raw_checklist)
        checklist_states = self._build_checklist_states(
            step, raw_checklist, cleaned_checklist
        )

        payload = {
            "slots": self._serialise_slots(step, cleaned_slots),
            "checklist": self._serialise_checklist(checklist_states),
        }
        step_state = models.ProcedureRunStepState(
            run_id=run.id,
            step_key=step.key,
            payload=payload,
        )
        self._db.add(step_state)

        self._persist_slot_values(run, step, cleaned_slots)
        self._persist_checklist_states(run, checklist_states)

        previous_state = run.state
        previous_closed_at = run.closed_at

        self._transition_to_in_progress(run)

        expected_total = len(run.procedure.steps)
        committed_total = len(snapshot.step_states) + 1
        if committed_total >= expected_total:
            self._transition_to_completed(run)

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

    def fail_run(
        self,
        *,
        run_id: str,
        actor: Optional[str] = None,
    ) -> RunSnapshot:
        """Mark the run as failed and record the transition."""

        run = self._load_run(run_id)
        self._ensure_run_active(run)

        previous_state = run.state
        previous_closed_at = run.closed_at

        self._transition_to_failed(run)

        self._db.flush()

        resolved_actor = actor or run.user_id
        audit.run_updated(
            self._db,
            actor=resolved_actor,
            run_id=run.id,
            before={
                "state": previous_state,
                "closed_at": previous_closed_at.isoformat() if previous_closed_at else None,
            },
            after={
                "state": run.state,
                "closed_at": run.closed_at.isoformat() if run.closed_at else None,
            },
        )

        self._db.refresh(run)
        return RunSnapshot(
            run=run,
            step_states={state.step_key: state for state in run.step_states},
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_run_active(self, run: models.ProcedureRun) -> ProcedureRunState:
        try:
            state = ProcedureRunState(run.state)
        except ValueError as exc:
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Unknown state transition from '{run.state}'",
            ) from exc

        if state in {ProcedureRunState.COMPLETED, ProcedureRunState.FAILED}:
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Run already terminal with state '{run.state}'",
            )
        return state

    def _transition_to_in_progress(self, run: models.ProcedureRun) -> bool:
        try:
            current_state = ProcedureRunState(run.state)
        except ValueError as exc:
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Unknown state transition from '{run.state}'",
            ) from exc

        if current_state == ProcedureRunState.PENDING:
            return self._apply_transition(run, ProcedureRunState.IN_PROGRESS)
        if current_state == ProcedureRunState.IN_PROGRESS:
            return False
        if not can_transition(current_state, ProcedureRunState.IN_PROGRESS):
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Cannot resume run in state '{run.state}'",
            )
        raise InvalidTransitionError(
            run_id=run.id,
            message=f"Unknown state transition from '{run.state}'",
        )

    def _transition_to_completed(self, run: models.ProcedureRun) -> bool:
        try:
            current_state = ProcedureRunState(run.state)
        except ValueError as exc:
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Cannot complete run from state '{run.state}'",
            ) from exc

        if current_state == ProcedureRunState.COMPLETED:
            return False
        if current_state == ProcedureRunState.FAILED:
            raise InvalidTransitionError(
                run_id=run.id,
                message="Cannot complete a failed run",
            )
        if not can_transition(current_state, ProcedureRunState.COMPLETED):
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Cannot complete run from state '{run.state}'",
            )
        return self._apply_transition(run, ProcedureRunState.COMPLETED)

    def _transition_to_failed(self, run: models.ProcedureRun) -> bool:
        try:
            current_state = ProcedureRunState(run.state)
        except ValueError as exc:
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Cannot fail run from state '{run.state}'",
            ) from exc

        if current_state == ProcedureRunState.FAILED:
            return False
        if current_state == ProcedureRunState.COMPLETED:
            raise InvalidTransitionError(
                run_id=run.id,
                message="Cannot fail a completed run",
            )
        if not can_transition(current_state, ProcedureRunState.FAILED):
            raise InvalidTransitionError(
                run_id=run.id,
                message=f"Cannot fail run from state '{run.state}'",
            )
        return self._apply_transition(run, ProcedureRunState.FAILED)

    def _apply_transition(
        self, run: models.ProcedureRun, target: ProcedureRunState
    ) -> bool:
        previous_state = run.state
        try:
            apply_transition(run, target, now=self._now)
        except ProcedureFSMInvalidTransitionError as exc:
            raise InvalidTransitionError(
                run_id=run.id,
                message=(
                    f"Cannot transition run from '{previous_state}' to '{target.value}'"
                ),
            ) from exc
        return run.state != previous_state

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

    def _slot_definition(self, slot: Any) -> SlotDefinition:
        metadata: Dict[str, Any]
        if isinstance(slot, Mapping):
            name = str(slot.get("name") or slot.get("key") or "")
            slot_type = str(slot.get("type") or slot.get("slot_type") or "string")
            required = bool(slot.get("required", False))
            metadata = dict(slot.get("metadata") or slot.get("configuration") or {})
            options = slot.get("options")
            mask = slot.get("mask") or metadata.get("mask")
            validate = slot.get("validate") or metadata.get("validate")
            if options is not None and "options" not in metadata:
                metadata["options"] = options
            if mask and "mask" not in metadata:
                metadata["mask"] = mask
            if validate and "validate" not in metadata:
                metadata["validate"] = validate
        else:
            name = str(getattr(slot, "name", getattr(slot, "key", "")))
            slot_type = str(getattr(slot, "slot_type", getattr(slot, "type", "string")))
            required = bool(getattr(slot, "required", False))
            metadata = dict(getattr(slot, "configuration", {}) or {})
            options = metadata.get("options") or metadata.get("choices")
            mask = metadata.get("mask")
            validate = metadata.get("validate") or metadata.get("pattern")
            if options is not None and "options" not in metadata:
                metadata["options"] = options
            if mask and "mask" not in metadata:
                metadata["mask"] = mask
            if validate and "validate" not in metadata:
                metadata["validate"] = validate

        definition: SlotDefinition = {
            "name": name,
            "type": slot_type,
            "required": required,
            "metadata": metadata,
        }
        if options is not None:
            definition["options"] = options
        if mask:
            definition["mask"] = mask
        if validate:
            definition["validate"] = validate
        return definition

    def _validate_slots(self, step: models.ProcedureStep, slots: Dict[str, Any]) -> Dict[str, Any]:
        definitions = [self._slot_definition(slot) for slot in step.slots]
        validator = SlotValidator(definitions)
        try:
            return validator.validate(dict(slots))
        except ProcedureSlotValidationError as exc:
            issues = getattr(exc, "issues", [])
            formatted = []
            for issue in issues:
                slot = issue.get("slot") or issue.get("field")
                formatted.append(
                    {
                        "field": slot,
                        "code": issue.get("code", "invalid"),
                        "params": dict(issue.get("params") or {}),
                    }
                )
            if not formatted:
                formatted = [
                    {
                        "field": None,
                        "code": "invalid",
                        "params": {"message": str(exc)},
                    }
                ]
            raise SlotValidationError(formatted) from exc

    def _next_pending_step(
        self, run: models.ProcedureRun, step_states: Dict[str, models.ProcedureRunStepState]
    ) -> Optional[models.ProcedureStep]:
        ordered_steps = sorted(run.procedure.steps, key=lambda item: item.position)
        for step in ordered_steps:
            if step.key not in step_states:
                return step
        return None

    def _checklist_definitions(self, step: models.ProcedureStep) -> List[Dict[str, Any]]:
        definitions: List[Dict[str, Any]] = []
        for item in step.checklist_items:
            metadata = {"label": item.label}
            if item.description:
                metadata["description"] = item.description
            definitions.append(
                {
                    "name": item.key,
                    "required": item.required,
                    "metadata": metadata,
                }
            )
        return definitions

    def _validate_checklist(
        self, step: models.ProcedureStep, checklist: List[Dict[str, Any]]
    ) -> Dict[str, bool]:
        validator = ChecklistValidator(self._checklist_definitions(step))
        try:
            return validator.validate(checklist)
        except ProcedureChecklistValidationError as exc:
            issues = getattr(exc, "issues", None)
            if not issues:
                issues = [
                    {"field": "checklist", "code": "validation.invalid", "params": {"message": str(exc)}}
                ]
            raise ChecklistValidationError(issues) from exc

    def _build_checklist_states(
        self,
        step: models.ProcedureStep,
        checklist: List[Dict[str, Any]],
        cleaned: Mapping[str, bool],
    ) -> List[Dict[str, Any]]:
        submissions = {
            item["key"]: item
            for item in checklist
            if isinstance(item, Mapping) and "key" in item
        }
        states: List[Dict[str, Any]] = []
        for item in step.checklist_items:
            submitted = submissions.get(item.key, {})
            completed = bool(cleaned.get(item.key, False))
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
