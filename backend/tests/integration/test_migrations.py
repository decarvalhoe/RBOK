"""Regression tests for Alembic migrations."""

from __future__ import annotations

import os
from importlib import reload
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _make_alembic_config(database_url: str) -> Config:
    """Return an Alembic config bound to a temporary SQLite database."""

    base_path = Path(__file__).resolve().parents[2]
    config = Config(str(base_path / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("script_location", str(base_path / "alembic"))
    # Tests should be quiet and rely on pytest's own logging.
    config.attributes["configure_logger"] = False
    return config


def test_procedural_schema_constraints(tmp_path) -> None:
    """Ensure the procedural schema migration adds the expected constraints."""

    os.environ.setdefault("RBOK_SKIP_MAIN_IMPORT", "1")
    db_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = database_url
    # Ensure Alembic picks up the fresh database URL by reloading the module.
    from app import database as database_module

    reload(database_module)
    config = _make_alembic_config(database_url)

    # Start from the original schema and then apply the new revision under test.
    command.upgrade(config, "e5f9bb2ca398")
    command.upgrade(config, "0f9a441a8cda")

    assert db_path.exists(), "database file was not created"

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "procedure_slots" in tables, f"procedure_slots table missing, existing: {tables}"

        slot_constraints = inspector.get_unique_constraints("procedure_slots")
        assert any(
            constraint["name"] == "uq_procedure_slot_name"
            and set(constraint["column_names"]) == {"step_id", "name"}
            for constraint in slot_constraints
        ), "procedure_slots.unique(step_id, name) missing"

        checklist_constraints = inspector.get_unique_constraints(
            "procedure_step_checklist_items"
        )
        assert any(
            constraint["name"] == "uq_procedure_step_checklist_key"
            and set(constraint["column_names"]) == {"step_id", "key"}
            for constraint in checklist_constraints
        ), "procedure_step_checklist_items.unique(step_id, key) missing"

        run_value_constraints = inspector.get_unique_constraints("procedure_run_slot_values")
        assert any(
            constraint["name"] == "uq_procedure_run_slot_value"
            and set(constraint["column_names"]) == {"run_id", "slot_id"}
            for constraint in run_value_constraints
        ), "procedure_run_slot_values.unique(run_id, slot_id) missing"

    finally:
        engine.dispose()
