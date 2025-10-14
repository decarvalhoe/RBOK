"""Finite state machine describing the lifecycle of a procedure run."""
from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable, Set, Union


class ProcedureRunState(str, Enum):
    """Allowed lifecycle states for a :class:`~app.models.ProcedureRun`."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcedureRunStateError(RuntimeError):
    """Base exception for procedure run state errors."""


class UnknownProcedureRunState(ProcedureRunStateError):
    """Raised when attempting to use an unknown state name."""

    def __init__(self, state: Union[str, ProcedureRunState]) -> None:
        super().__init__(f"Unknown procedure run state: {state}")
        self.state = state


class InvalidProcedureRunTransition(ProcedureRunStateError):
    """Raised when an invalid transition between two states is requested."""

    def __init__(self, current: ProcedureRunState, target: ProcedureRunState) -> None:
        super().__init__(
            f"Cannot transition procedure run from '{current.value}' to '{target.value}'"
        )
        self.current = current
        self.target = target


_VALID_TRANSITIONS: Dict[ProcedureRunState, Set[ProcedureRunState]] = {
    ProcedureRunState.PENDING: {ProcedureRunState.IN_PROGRESS, ProcedureRunState.FAILED},
    ProcedureRunState.IN_PROGRESS: {
        ProcedureRunState.COMPLETED,
        ProcedureRunState.FAILED,
    },
    ProcedureRunState.COMPLETED: set(),
    ProcedureRunState.FAILED: set(),
}

_TERMINAL_STATES: Set[ProcedureRunState] = {
    ProcedureRunState.COMPLETED,
    ProcedureRunState.FAILED,
}

_StateLike = Union[str, ProcedureRunState]


def _ensure_state(value: _StateLike) -> ProcedureRunState:
    if isinstance(value, ProcedureRunState):
        return value
    try:
        return ProcedureRunState(str(value))
    except ValueError as exc:  # pragma: no cover - defensive
        raise UnknownProcedureRunState(value) from exc


def valid_transitions(state: _StateLike) -> Set[ProcedureRunState]:
    """Return the set of states that ``state`` can transition to."""

    return set(_VALID_TRANSITIONS[_ensure_state(state)])


def can_transition(current: _StateLike, target: _StateLike) -> bool:
    """Return ``True`` when the transition between ``current`` and ``target`` is valid."""

    current_state = _ensure_state(current)
    target_state = _ensure_state(target)
    if current_state == target_state:
        return True
    return target_state in _VALID_TRANSITIONS[current_state]


def assert_transition(current: _StateLike, target: _StateLike) -> ProcedureRunState:
    """Ensure the requested transition is valid, raising if not."""

    current_state = _ensure_state(current)
    target_state = _ensure_state(target)
    if not can_transition(current_state, target_state):
        raise InvalidProcedureRunTransition(current_state, target_state)
    return target_state


def is_terminal_state(state: _StateLike) -> bool:
    """Return ``True`` when ``state`` is a terminal state in the FSM."""

    return _ensure_state(state) in _TERMINAL_STATES


def all_states() -> Iterable[ProcedureRunState]:
    """Yield all available states of the state machine."""

    return ProcedureRunState


__all__ = [
    "ProcedureRunState",
    "ProcedureRunStateError",
    "UnknownProcedureRunState",
    "InvalidProcedureRunTransition",
    "valid_transitions",
    "can_transition",
    "assert_transition",
    "is_terminal_state",
    "all_states",
]
