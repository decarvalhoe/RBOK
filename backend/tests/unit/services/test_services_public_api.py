"""Regression tests for :mod:`app.services` public exports."""

from app.services import ProcedureRunService as ExportedProcedureRunService
from app.services.procedure_runs import (
    ChecklistValidationError as ProcedureRunChecklistValidationError,
    InvalidTransitionError as ProcedureRunInvalidTransitionError,
    ProcedureNotFoundError as ProcedureRunProcedureNotFoundError,
    ProcedureRunNotFoundError as ProcedureRunNotFoundError,
    ProcedureRunService as ModuleProcedureRunService,
    RunSnapshot as ProcedureRunSnapshot,
    SlotValidationError as ProcedureRunSlotValidationError,
)
from app.services.procedures import runs as procedures_runs_module
from app.services.procedures import service as procedures_service_module


def test_procedure_run_service_export_aliases_module() -> None:
    """Ensure the public service export forwards to the consolidated module."""

    assert ExportedProcedureRunService is ModuleProcedureRunService


def test_procedures_service_module_proxies_canonical_exports() -> None:
    """The legacy service module should proxy the canonical implementation."""

    assert procedures_service_module.ProcedureRunService is ModuleProcedureRunService
    assert (
        procedures_service_module.ProcedureNotFoundError
        is ProcedureRunProcedureNotFoundError
    )
    assert (
        procedures_service_module.ProcedureRunNotFoundError
        is ProcedureRunNotFoundError
    )
    assert (
        procedures_service_module.InvalidTransitionError
        is ProcedureRunInvalidTransitionError
    )
    assert procedures_service_module.SlotValidationError is ProcedureRunSlotValidationError
    assert (
        procedures_service_module.ChecklistValidationError
        is ProcedureRunChecklistValidationError
    )
    assert procedures_service_module.RunSnapshot is ProcedureRunSnapshot


def test_procedures_runs_module_proxies_canonical_exports() -> None:
    """The intermediate ``procedures.runs`` module should mirror public exports."""

    assert procedures_runs_module.ProcedureRunService is ModuleProcedureRunService
    assert (
        procedures_runs_module.ProcedureNotFoundError
        is ProcedureRunProcedureNotFoundError
    )
    assert (
        procedures_runs_module.ProcedureRunNotFoundError is ProcedureRunNotFoundError
    )
    assert (
        procedures_runs_module.InvalidTransitionError
        is ProcedureRunInvalidTransitionError
    )
    assert procedures_runs_module.SlotValidationError is ProcedureRunSlotValidationError
    assert (
        procedures_runs_module.ChecklistValidationError
        is ProcedureRunChecklistValidationError
    )
    assert procedures_runs_module.RunSnapshot is ProcedureRunSnapshot
