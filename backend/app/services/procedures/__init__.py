"""Procedure-related service helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .exceptions import (
    ChecklistValidationError,
    InvalidTransitionError,
    SlotValidationError,
    StepNotFoundError,
    StepOrderError,
)
from .fsm import (
    ProcedureRunState,
    TERMINAL_STATES,
    apply_transition,
    can_transition,
    is_terminal_state,
)
from .validators import ChecklistValidator, SlotValidator
from ..procedure_definitions import ProcedureService

if TYPE_CHECKING:  # pragma: no cover - import-time type checking only
    from ..procedure_runs import (
        InvalidTransitionError as ProcedureRunInvalidTransitionError,
        ProcedureRunService as ProcedureRunLifecycleService,
    )


def __getattr__(name: str):  # pragma: no cover - simple attribute proxy
    if name in {"ProcedureRunService", "InvalidProcedureRunTransition"}:
        from ..procedure_runs import (
            InvalidTransitionError as ProcedureRunInvalidTransitionError,
            ProcedureRunService as ProcedureRunLifecycleService,
        )

        mapping = {
            "ProcedureRunService": ProcedureRunLifecycleService,
            "InvalidProcedureRunTransition": ProcedureRunInvalidTransitionError,
        }
        value = mapping[name]
        globals()[name] = value
        return value
    raise AttributeError(name)

__all__ = [
    "ProcedureRunState",
    "TERMINAL_STATES",
    "apply_transition",
    "can_transition",
    "is_terminal_state",
    "ProcedureFSM",
    "ProcedureService",
    "ProcedureRunService",
    "ChecklistValidationError",
    "InvalidTransitionError",
    "InvalidProcedureRunTransition",
    "SlotValidationError",
    "StepNotFoundError",
    "StepOrderError",
    "ChecklistValidator",
    "SlotValidator",
]
