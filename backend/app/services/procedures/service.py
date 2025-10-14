"""Domain service orchestrating procedure run progression."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import models
from .. import audit
from .fsm import ProcedureRunState, assert_transition, can_transition, is_terminal_state


class ProcedureRunService:
    """Provide helpers to manipulate :class:`~app.models.ProcedureRun` instances."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def can_transition(self, run: models.ProcedureRun, target: ProcedureRunState | str) -> bool:
        """Return whether ``run`` can transition to ``target``."""

        return can_transition(run.state, target)

    def transition_run(
        self,
        run: models.ProcedureRun,
        target: ProcedureRunState | str,
        *,
        actor: str,
    ) -> models.ProcedureRun:
        """Transition ``run`` to ``target`` while enforcing the FSM and auditing."""

        current_state = ProcedureRunState(run.state)
        target_state = assert_transition(current_state, target)
        if current_state == target_state:
            return run

        before_payload = self._serialise_run(run)

        run.state = target_state.value
        run.closed_at = datetime.utcnow() if is_terminal_state(target_state) else None

        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)

        audit.run_updated(
            self._db,
            actor=actor,
            run_id=run.id,
            before=before_payload,
            after=self._serialise_run(run),
        )
        return run

    def commit_step(
        self,
        run: models.ProcedureRun,
        *,
        step_key: str,
        payload: Dict[str, Any],
        actor: str,
    ) -> models.ProcedureRunStepState:
        """Persist the state of a step and record an audit trail entry."""

        statement = select(models.ProcedureRunStepState).where(
            models.ProcedureRunStepState.run_id == run.id,
            models.ProcedureRunStepState.step_key == step_key,
        )
        existing: Optional[models.ProcedureRunStepState] = self._db.execute(statement).scalar_one_or_none()
        before_payload: Optional[Dict[str, Any]] = None

        if existing is None:
            step_state = models.ProcedureRunStepState(
                run_id=run.id,
                step_key=step_key,
                payload=dict(payload),
            )
            self._db.add(step_state)
        else:
            step_state = existing
            before_payload = self._serialise_step(step_state)
            step_state.payload = dict(payload)
            step_state.committed_at = datetime.utcnow()
            self._db.add(step_state)

        self._db.commit()
        self._db.refresh(step_state)

        audit.step_committed(
            self._db,
            actor=actor,
            run_id=run.id,
            step_key=step_key,
            before=before_payload,
            after=self._serialise_step(step_state),
        )
        return step_state

    def get_step_progress(self, run: models.ProcedureRun) -> Dict[str, int]:
        """Return basic progress information for the provided ``run``."""

        procedure = run.procedure or self._db.get(models.Procedure, run.procedure_id)
        total_steps = len(procedure.steps) if procedure else 0

        result = self._db.execute(
            select(models.ProcedureRunStepState.step_key).where(
                models.ProcedureRunStepState.run_id == run.id
            )
        )
        committed_count = len(result.all())
        remaining = max(total_steps - committed_count, 0)
        return {
            "total": total_steps,
            "completed": committed_count,
            "remaining": remaining,
        }

    @staticmethod
    def _serialise_run(run: models.ProcedureRun) -> Dict[str, Any]:
        return {
            "id": run.id,
            "procedure_id": run.procedure_id,
            "user_id": run.user_id,
            "state": run.state,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "closed_at": run.closed_at.isoformat() if run.closed_at else None,
        }

    @staticmethod
    def _serialise_step(step_state: models.ProcedureRunStepState) -> Dict[str, Any]:
        return {
            "run_id": step_state.run_id,
            "step_key": step_state.step_key,
            "payload": dict(step_state.payload or {}),
            "committed_at": step_state.committed_at.isoformat()
            if step_state.committed_at
            else None,
        }


__all__ = ["ProcedureRunService", "ProcedureRunState"]
