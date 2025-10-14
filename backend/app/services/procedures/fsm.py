"""Finite state machine coordinating procedure run transitions."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from app import models

from .exceptions import (
    ChecklistValidationError,
    InvalidTransitionError,
    SlotValidationError,
    StepNotFoundError,
    StepOrderError,
)
from .validators import ChecklistValidator, SlotValidator

RUN_PENDING = "pending"
RUN_IN_PROGRESS = "in_progress"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"
TERMINAL_STATES = {RUN_COMPLETED, RUN_FAILED}


class ProcedureFSM:
    """Coordinate the lifecycle of a :class:`~app.models.ProcedureRun`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Run lifecycle helpers
    # ------------------------------------------------------------------
    def start(self, run: models.ProcedureRun) -> models.ProcedureRun:
        if run.state != RUN_PENDING:
            raise InvalidTransitionError(f"Cannot start run from state '{run.state}'")
        run.state = RUN_IN_PROGRESS
        self._db.add(run)
        self._db.flush()
        return run

    def fail(self, run: models.ProcedureRun, reason: Optional[str] = None) -> models.ProcedureRun:
        if run.state in TERMINAL_STATES:
            raise InvalidTransitionError(f"Run already terminal: {run.state}")
        run.state = RUN_FAILED
        run.closed_at = datetime.utcnow()
        if reason:
            payload = {"reason": reason}
            state = models.ProcedureRunStepState(
                run_id=run.id,
                step_key="__terminal__",
                payload=payload,
            )
            self._db.add(state)
        self._db.add(run)
        self._db.flush()
        return run

    # ------------------------------------------------------------------
    # Step handling
    # ------------------------------------------------------------------
    def commit_step(
        self,
        run: models.ProcedureRun,
        step_key: str,
        slots: Optional[Dict[str, Any]] = None,
        checklist: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> models.ProcedureRunStepState:
        if run.state in TERMINAL_STATES:
            raise InvalidTransitionError(f"Cannot commit steps when run is {run.state}")

        procedure = self._load_procedure(run)
        step = self._get_step(procedure, step_key)
        expected_key = self._expected_step_key(run, procedure)
        if expected_key and step.key != expected_key:
            raise StepOrderError(
                f"Step '{step.key}' cannot be committed before '{expected_key}'"
            )

        slot_validator = SlotValidator(step.slots or [])
        checklist_validator = ChecklistValidator(step.checklist or [])

        try:
            validated_slots = slot_validator.validate(slots or {})
            validated_checklist = checklist_validator.validate(checklist)
        except SlotValidationError:
            raise
        except ChecklistValidationError:
            raise

        payload = {"slots": validated_slots, "checklist": validated_checklist}
        state = models.ProcedureRunStepState(
            run_id=run.id,
            step_key=step.key,
            payload=payload,
        )
        self._db.add(state)

        if run.state == RUN_PENDING:
            run.state = RUN_IN_PROGRESS
        if self._is_last_step(step, procedure):
            run.state = RUN_COMPLETED
            run.closed_at = datetime.utcnow()
        self._db.add(run)
        self._db.flush()
        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_procedure(self, run: models.ProcedureRun) -> models.Procedure:
        procedure = run.procedure
        if procedure is None:
            procedure = self._db.get(models.Procedure, run.procedure_id)
        if procedure is None:
            raise StepNotFoundError("Associated procedure not found")
        return procedure

    def _get_step(self, procedure: models.Procedure, step_key: str) -> models.ProcedureStep:
        for step in procedure.steps:
            if step.key == step_key:
                return step
        raise StepNotFoundError(f"Step '{step_key}' not found for procedure '{procedure.id}'")

    def _expected_step_key(
        self, run: models.ProcedureRun, procedure: models.Procedure
    ) -> Optional[str]:
        committed_keys = {
            state.step_key
            for state in self._db.query(models.ProcedureRunStepState)
            .filter_by(run_id=run.id)
            .all()
        }
        for step in sorted(procedure.steps, key=lambda item: item.position):
            if step.key not in committed_keys:
                return step.key
        return None

    def _is_last_step(
        self, step: models.ProcedureStep, procedure: models.Procedure
    ) -> bool:
        ordered = sorted(procedure.steps, key=lambda item: item.position)
        return ordered and ordered[-1].key == step.key


__all__ = [
    "ProcedureFSM",
    "RUN_PENDING",
    "RUN_IN_PROGRESS",
    "RUN_COMPLETED",
    "RUN_FAILED",
]
