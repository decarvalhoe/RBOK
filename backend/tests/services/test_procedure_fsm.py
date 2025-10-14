from __future__ import annotations

from datetime import datetime

import pytest

from app import models
from app.services.procedures import (
    ProcedureRunState,
    apply_transition,
    can_transition,
    is_terminal_state,
)
from app.services.procedures.exceptions import InvalidTransitionError


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProcedureRunState.PENDING, ProcedureRunState.PENDING),
        (ProcedureRunState.PENDING, ProcedureRunState.IN_PROGRESS),
        (ProcedureRunState.PENDING, ProcedureRunState.FAILED),
        (ProcedureRunState.IN_PROGRESS, ProcedureRunState.IN_PROGRESS),
        (ProcedureRunState.IN_PROGRESS, ProcedureRunState.COMPLETED),
        (ProcedureRunState.IN_PROGRESS, ProcedureRunState.FAILED),
        (ProcedureRunState.COMPLETED, ProcedureRunState.COMPLETED),
        (ProcedureRunState.FAILED, ProcedureRunState.FAILED),
    ],
)
def test_can_transition_allows_expected_moves(
    current: ProcedureRunState, target: ProcedureRunState
) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProcedureRunState.PENDING, ProcedureRunState.COMPLETED),
        (ProcedureRunState.IN_PROGRESS, ProcedureRunState.PENDING),
        (ProcedureRunState.COMPLETED, ProcedureRunState.IN_PROGRESS),
        (ProcedureRunState.COMPLETED, ProcedureRunState.FAILED),
        (ProcedureRunState.FAILED, ProcedureRunState.PENDING),
        (ProcedureRunState.FAILED, ProcedureRunState.IN_PROGRESS),
    ],
)
def test_can_transition_rejects_invalid_moves(
    current: ProcedureRunState, target: ProcedureRunState
) -> None:
    assert not can_transition(current, target)


def test_apply_transition_updates_state_and_closed_at() -> None:
    run = models.ProcedureRun(state=ProcedureRunState.PENDING.value)

    apply_transition(run, ProcedureRunState.IN_PROGRESS)

    assert run.state == ProcedureRunState.IN_PROGRESS.value
    assert run.closed_at is None

    apply_transition(run, ProcedureRunState.FAILED)

    assert run.state == ProcedureRunState.FAILED.value
    assert isinstance(run.closed_at, datetime)


def test_apply_transition_rejects_invalid_move() -> None:
    run = models.ProcedureRun(state=ProcedureRunState.COMPLETED.value)

    with pytest.raises(InvalidTransitionError):
        apply_transition(run, ProcedureRunState.IN_PROGRESS)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (ProcedureRunState.PENDING, False),
        (ProcedureRunState.IN_PROGRESS, False),
        (ProcedureRunState.COMPLETED, True),
        (ProcedureRunState.FAILED, True),
    ],
)
def test_is_terminal_state_reports_expected_values(
    state: ProcedureRunState, expected: bool
) -> None:
    assert is_terminal_state(state) is expected
