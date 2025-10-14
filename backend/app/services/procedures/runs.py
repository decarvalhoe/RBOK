from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Sequence, Set

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...models import (
    Procedure,
    ProcedureRun,
    ProcedureRunChecklistItemState,
    ProcedureRunStepState,
    ProcedureStep,
)


class ProcedureRunNotFoundError(LookupError):
    """Raised when a procedure run could not be located."""


class ProcedureStepNotFoundError(LookupError):
    """Raised when a step key is unknown for the current procedure."""


class InvalidChecklistItemError(ValueError):
    """Raised when checklist identifiers do not belong to the targeted step."""

    def __init__(self, invalid_item_ids: Sequence[str]):
        super().__init__("Checklist items do not belong to the requested step")
        self.invalid_item_ids = list(invalid_item_ids)


class ChecklistIncompleteError(ValueError):
    """Raised when a step transition is attempted with incomplete checklist items."""

    def __init__(self, missing_item_ids: Sequence[str]):
        super().__init__("Checklist items must be completed before committing the step")
        self.missing_item_ids = list(missing_item_ids)


@dataclass
class _ChecklistUpdateResult:
    missing_item_ids: List[str]


class ProcedureRunService:
    """Coordinate progression of procedure runs and associated validations."""

    def __init__(self, session: Session):
        self._session = session

    def get_run(self, run_id: str) -> ProcedureRun:
        """Return a run with all related objects eagerly loaded."""

        stmt = (
            select(ProcedureRun)
            .where(ProcedureRun.id == run_id)
            .options(
                selectinload(ProcedureRun.procedure)
                .selectinload(Procedure.steps)
                .selectinload(ProcedureStep.checklist_items),
                selectinload(ProcedureRun.step_states),
                selectinload(ProcedureRun.checklist_states).selectinload(
                    ProcedureRunChecklistItemState.checklist_item
                ),
            )
        )
        run = self._session.execute(stmt).scalars().unique().one_or_none()
        if run is None:
            raise ProcedureRunNotFoundError(run_id)
        return run

    def commit_step(
        self,
        run_id: str,
        step_key: str,
        payload: Dict[str, object],
        completed_checklist_item_ids: Iterable[str] | None = None,
    ) -> ProcedureRun:
        """Persist a step payload and update checklist state for a run."""

        run = self.get_run(run_id)
        step = self._find_step(run, step_key)
        self._upsert_step_state(run, step_key, payload)
        checklist_result = self._apply_checklist_updates(
            run, step, set(completed_checklist_item_ids or [])
        )
        self._session.flush()
        if checklist_result.missing_item_ids:
            raise ChecklistIncompleteError(checklist_result.missing_item_ids)
        self._refresh_run_state(run)
        self._session.flush()
        return run

    def _find_step(self, run: ProcedureRun, step_key: str) -> ProcedureStep:
        for step in run.procedure.steps:
            if step.key == step_key:
                return step
        raise ProcedureStepNotFoundError(step_key)

    def _upsert_step_state(
        self, run: ProcedureRun, step_key: str, payload: Dict[str, object]
    ) -> ProcedureRunStepState:
        state = next((item for item in run.step_states if item.step_key == step_key), None)
        if state is None:
            state = ProcedureRunStepState(run_id=run.id, step_key=step_key)
            self._session.add(state)
            run.step_states.append(state)
        state.payload = payload
        state.committed_at = datetime.utcnow()
        return state

    def _apply_checklist_updates(
        self, run: ProcedureRun, step: ProcedureStep, completed_item_ids: Set[str]
    ) -> _ChecklistUpdateResult:
        step_item_ids = {item.id for item in step.checklist_items}
        invalid_ids = completed_item_ids - step_item_ids
        if invalid_ids:
            raise InvalidChecklistItemError(sorted(invalid_ids))
        missing_item_ids: List[str] = []
        existing_statuses = {
            status.checklist_item_id: status for status in run.checklist_states
        }
        for item in step.checklist_items:
            status = existing_statuses.get(item.id)
            if status is None:
                status = ProcedureRunChecklistItemState(
                    run_id=run.id, checklist_item_id=item.id
                )
                self._session.add(status)
                run.checklist_states.append(status)
            completed = item.id in completed_item_ids
            status.is_completed = completed
            status.completed_at = datetime.utcnow() if completed else None
            if not completed:
                missing_item_ids.append(item.id)
        return _ChecklistUpdateResult(missing_item_ids=missing_item_ids)

    def _refresh_run_state(self, run: ProcedureRun) -> None:
        if run.state == "pending":
            run.state = "in_progress"
        if self._is_run_completed(run):
            run.state = "completed"
            run.closed_at = datetime.utcnow()
        else:
            if run.state == "completed":
                run.state = "in_progress"
            if run.state != "pending":
                run.closed_at = None

    def _is_run_completed(self, run: ProcedureRun) -> bool:
        step_keys = {step.key for step in run.procedure.steps}
        state_keys = {state.step_key for state in run.step_states}
        if step_keys - state_keys:
            return False
        statuses_by_item = {
            status.checklist_item_id: status for status in run.checklist_states
        }
        for step in run.procedure.steps:
            for item in step.checklist_items:
                status = statuses_by_item.get(item.id)
                if status is None or not status.is_completed:
                    return False
        return True
