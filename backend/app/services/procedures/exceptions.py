"""Domain-specific exceptions for the procedural services."""
from __future__ import annotations


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


class ChecklistValidationError(ValidationError):
    """Raised when checklist submissions are invalid."""


class DuplicateProcedureComponentError(ValidationError):
    """Raised when procedure components reuse the same identifier."""
