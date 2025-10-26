"""Regression tests for :mod:`app.services` public exports."""

import sys
from importlib import import_module

import pytest

from app.services import ProcedureRunService as ExportedProcedureRunService
from app.services.procedure_runs import ProcedureRunService as ModuleProcedureRunService


def test_procedure_run_service_export_aliases_module() -> None:
    """Ensure the public service export forwards to the consolidated module."""

    assert ExportedProcedureRunService is ModuleProcedureRunService


def test_procedures_package_no_longer_proxies_service_exports() -> None:
    """Importing :mod:`app.services.procedures` should not expose run services."""

    procedures_module = import_module("app.services.procedures")

    assert hasattr(procedures_module, "ProcedureRunState")
    sentinel = object()
    assert getattr(procedures_module, "ProcedureRunService", sentinel) is sentinel


def test_procedures_submodules_are_removed() -> None:
    """Importing removed compatibility modules should raise :class:`ModuleNotFoundError`."""

    sys.modules.pop("app.services.procedures.service", None)
    sys.modules.pop("app.services.procedures.runs", None)
    with pytest.raises(ModuleNotFoundError):
        import_module("app.services.procedures.service")

    with pytest.raises(ModuleNotFoundError):
        import_module("app.services.procedures.runs")
