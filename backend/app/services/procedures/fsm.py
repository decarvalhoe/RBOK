"""Finite state machine helpers for procedure runs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, FrozenSet

from app import models

from .exceptions import InvalidTransitionError


class ProcedureRunState(str, Enum):
    """Enumeration of supported procedure run states."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATES: FrozenSet[ProcedureRunState] = frozenset(
    {ProcedureRunState.COMPLETED, ProcedureRunState.FAILED}
)

_ALLOWED_TRANSITIONS: Dict[ProcedureRunState, FrozenSet[ProcedureRunState]] = {
    ProcedureRunState.PENDING: frozenset(
        {
            ProcedureRunState.PENDING,
            ProcedureRunState.IN_PROGRESS,
            ProcedureRunState.FAILED,
        }
    ),
    ProcedureRunState.IN_PROGRESS: frozenset(
        {
            ProcedureRunState.IN_PROGRESS,
            ProcedureRunState.COMPLETED,
            ProcedureRunState.FAILED,
        }
    ),
    ProcedureRunState.COMPLETED: frozenset({ProcedureRunState.COMPLETED}),
    ProcedureRunState.FAILED: frozenset({ProcedureRunState.FAILED}),
}


def _coerce_state(value: ProcedureRunState | str) -> ProcedureRunState:
    """Normalise ``value`` into a :class:`ProcedureRunState` instance."""

    if isinstance(value, ProcedureRunState):
        return value
    try:
        return ProcedureRunState(value)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise InvalidTransitionError(f"Unknown procedure run state '{value}'") from exc


def is_terminal_state(state: ProcedureRunState | str) -> bool:
    """Return whether ``state`` represents a terminal run state."""

    return _coerce_state(state) in TERMINAL_STATES


def can_transition(
    current: ProcedureRunState | str, target: ProcedureRunState | str
) -> bool:
    """Return whether a run in ``current`` state can reach ``target``."""

    current_state = _coerce_state(current)
    target_state = _coerce_state(target)
    return target_state in _ALLOWED_TRANSITIONS[current_state]


def apply_transition(
    run: models.ProcedureRun, target: ProcedureRunState | str
) -> models.ProcedureRun:
    """Transition ``run`` to ``target`` if the move is permitted."""

    target_state = _coerce_state(target)
    if not can_transition(run.state, target_state):
        raise InvalidTransitionError(
            f"Cannot transition run from '{run.state}' to '{target_state.value}'"
        )

    current_state = _coerce_state(run.state)
    if current_state == target_state:
        return run

    run.state = target_state.value
    if target_state in TERMINAL_STATES:
        if run.closed_at is None:
            run.closed_at = datetime.utcnow()
    else:
        run.closed_at = None
    return run


__all__ = [
    "ProcedureRunState",
    "TERMINAL_STATES",
    "can_transition",
    "apply_transition",
    "is_terminal_state",
]
