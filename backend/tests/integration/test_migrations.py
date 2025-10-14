"""Regression tests for Alembic migrations."""

from __future__ import annotations

import os
from importlib import reload
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, table, column, insert, JSON, String, Text, Integer, Boolean


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

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            procedures = table(
                "procedures",
                column("id", String()),
                column("name", String(255)),
                column("description", Text()),
                column("metadata", JSON()),
            )
            steps = table(
                "procedure_steps",
                column("id", String()),
                column("procedure_id", String()),
                column("key", String(255)),
                column("title", String(255)),
                column("prompt", Text()),
                column("slots", JSON()),
                column("metadata", JSON()),
                column("checklists", JSON()),
                column("position", Integer()),
            )

            conn.execute(
                insert(procedures),
                [
                    {
                        "id": "legacy-procedure",
                        "name": "Legacy procedure",
                        "description": "Legacy description",
                        "metadata": {},
                    }
                ],
            )
            conn.execute(
                insert(steps),
                [
                    {
                        "id": "legacy-step",
                        "procedure_id": "legacy-procedure",
                        "key": "legacy-step",
                        "title": "Legacy Step",
                        "prompt": "Collect legacy payload",
                        "slots": [
                            {
                                "id": "slot-email",
                                "name": "email",
                                "label": "Email",
                                "type": "email",
                                "required": True,
                                "position": 3,
                                "metadata": {"domain": "example.com"},
                            },
                            {
                                "name": "verification_code",
                                "required": False,
                                "position": 1,
                            },
                        ],
                        "metadata": {},
                        "checklists": [
                            {
                                "id": "check-privacy",
                                "key": "privacy_ack",
                                "label": "Acknowledge privacy",
                                "description": "Confirm privacy notice",
                                "required": True,
                                "position": 2,
                            },
                            {
                                "name": "safety_briefing",
                                "required": False,
                            },
                        ],
                        "position": 0,
                    }
                ],
            )

        command.upgrade(config, "0f9a441a8cda")

        assert db_path.exists(), "database file was not created"

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "procedure_slots" in tables, f"procedure_slots table missing, existing: {tables}"

        step_columns = {column_info["name"] for column_info in inspector.get_columns("procedure_steps")}
        assert "slots" not in step_columns
        assert "checklists" not in step_columns

        slots_table = table(
            "procedure_slots",
            column("id", String()),
            column("step_id", String()),
            column("name", String()),
            column("label", String()),
            column("type", String()),
            column("required", Boolean()),
            column("position", Integer()),
            column("configuration", JSON()),
        )
        checklist_table = table(
            "procedure_step_checklist_items",
            column("id", String()),
            column("step_id", String()),
            column("key", String()),
            column("label", String()),
            column("description", Text()),
            column("required", Boolean()),
            column("position", Integer()),
        )

        with engine.connect() as conn:
            slot_rows = (
                conn.execute(
                    select(slots_table).where(slots_table.c.step_id == "legacy-step")
                )
                .mappings()
                .all()
            )
            assert len(slot_rows) == 2
            slots_by_name = {row["name"]: row for row in slot_rows}
            email_slot = slots_by_name["email"]
            assert email_slot["id"] == "slot-email"
            assert email_slot["label"] == "Email"
            assert email_slot["type"] == "email"
            assert email_slot["required"] is True
            assert email_slot["configuration"] == {"domain": "example.com"}
            assert email_slot["position"] == 3

            verification_slot = slots_by_name["verification_code"]
            assert verification_slot["required"] is False
            assert verification_slot["configuration"] == {}
            assert verification_slot["position"] == 1

            checklist_rows = (
                conn.execute(
                    select(checklist_table).where(checklist_table.c.step_id == "legacy-step")
                )
                .mappings()
                .all()
            )
            assert len(checklist_rows) == 2
            checklist_by_key = {row["key"]: row for row in checklist_rows}
            privacy_item = checklist_by_key["privacy_ack"]
            assert privacy_item["id"] == "check-privacy"
            assert privacy_item["required"] is True
            assert privacy_item["description"] == "Confirm privacy notice"
            assert privacy_item["position"] == 2

            safety_item = checklist_by_key["safety_briefing"]
            assert safety_item["label"] == "safety_briefing"
            assert safety_item["required"] is False

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
