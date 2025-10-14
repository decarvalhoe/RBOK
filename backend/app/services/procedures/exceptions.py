"""Domain-specific exceptions for the procedural services."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class ProcedureError(Exception):
    """Base class for procedural service errors."""


class InvalidTransitionError(ProcedureError):
    """Raised when attempting an invalid state transition."""


class StepNotFoundError(ProcedureError):
    """Raised when a procedure step cannot be located."""


class StepOrderError(ProcedureError):
    """Raised when steps are committed out of order."""


class ValidationError(ProcedureError):
    """Base class for validation errors."""


class SlotValidationError(ValidationError):
    """Raised when slot values fail validation."""

    def __init__(
        self,
        message: str,
        *,
        issues: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        super().__init__(message)
        self.issues = issues or []


class ChecklistValidationError(ValidationError):
    """Raised when checklist submissions are invalid."""

    def __init__(
        self,
        message: str,
        *,
        issues: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        super().__init__(message)
        self.issues = issues or []
