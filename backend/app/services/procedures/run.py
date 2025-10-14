from __future__ import annotations

"""Service layer orchestrating procedure run steps."""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import models
from .exceptions import InvalidTransitionError
from .fsm import ProcedureRunState, apply_transition, can_transition
from .validators import SlotDefinition, ValidationError, validate_payload


class ProcedureRunService:
    """Coordinates validation and persistence of procedure runs."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _get_run(self, run_id: str) -> models.ProcedureRun:
        run = self._db.get(models.ProcedureRun, run_id)
        if run is None:
            raise LookupError(f"Procedure run '{run_id}' not found")
        return run

    def _get_step(self, procedure_id: str, step_key: str) -> models.ProcedureStep:
        stmt = (
            select(models.ProcedureStep)
            .where(
                models.ProcedureStep.procedure_id == procedure_id,
                models.ProcedureStep.key == step_key,
            )
            .limit(1)
        )
        step = self._db.execute(stmt).scalar_one_or_none()
        if step is None:
            raise LookupError(
                f"Step '{step_key}' not found for procedure '{procedure_id}'"
            )
        return step

    def _get_step_state(
        self, run_id: str, step_key: str
    ) -> Optional[models.ProcedureRunStepState]:
        stmt = (
            select(models.ProcedureRunStepState)
            .where(
                models.ProcedureRunStepState.run_id == run_id,
                models.ProcedureRunStepState.step_key == step_key,
            )
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def commit_step(
        self,
        *,
        run_id: str,
        step_key: str,
        payload: Dict[str, Any],
    ) -> Tuple[Optional[models.ProcedureRunStepState], List[ValidationError]]:
        """Validate and persist a payload for a specific step.

        Returns a tuple of (state, errors). When errors are present, no data is
        persisted and the state is ``None``. Errors are structured with codes
        suitable for localisation.
        """

        run = self._get_run(run_id)
        if not can_transition(run.state, ProcedureRunState.IN_PROGRESS):
            raise InvalidTransitionError(
                f"Run '{run_id}' cannot accept new steps from state '{run.state}'"
            )

        step = self._get_step(run.procedure_id, step_key)

        slot_definitions: Iterable[SlotDefinition] = step.slots or []
        cleaned_payload, errors = validate_payload(slot_definitions, payload)
        if errors:
            return None, errors

        state = self._get_step_state(run.id, step_key)
        if state is None:
            state = models.ProcedureRunStepState(
                run_id=run.id,
                step_key=step_key,
                payload=cleaned_payload,
            )
        else:
            state.payload = cleaned_payload
            state.committed_at = datetime.utcnow()

        self._db.add(state)
        apply_transition(run, ProcedureRunState.IN_PROGRESS)
        self._db.add(run)
        self._db.commit()
        self._db.refresh(state)
        return state, []


__all__ = ["ProcedureRunService"]
