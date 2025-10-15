"""Regression tests for :mod:`app.services` public exports."""

from app.services import ProcedureRunService as ExportedProcedureRunService
from app.services.procedure_runs import ProcedureRunService as ModuleProcedureRunService


def test_procedure_run_service_export_aliases_module() -> None:
    """Ensure the public service export forwards to the consolidated module."""

    assert ExportedProcedureRunService is ModuleProcedureRunService
