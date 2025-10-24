from app.services.procedure_runs import (
    InvalidTransitionError,
    ProcedureNotFoundError,
    ProcedureRunNotFoundError,
)


def test_procedure_not_found_error_includes_identifier() -> None:
    error = ProcedureNotFoundError("proc-123")

    assert error.procedure_id == "proc-123"
    assert "proc-123" in str(error)


def test_procedure_run_not_found_error_includes_identifier() -> None:
    error = ProcedureRunNotFoundError("run-789")

    assert error.run_id == "run-789"
    assert "run-789" in str(error)


def test_invalid_transition_error_preserves_message() -> None:
    error = InvalidTransitionError(run_id="run-456", message="not allowed")

    assert error.run_id == "run-456"
    assert str(error) == "not allowed"
