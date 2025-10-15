"""Integration checks for the procedural normalization migration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_normalize_procedural_schema_migrates_payloads(tmp_path, monkeypatch):
    """Ensure legacy JSON payloads are faithfully migrated and reversible."""

    database_url = f"sqlite+pysqlite:///{tmp_path/'legacy.sqlite'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    alembic_cfg = Config(str(config_path))

    # Ensure Alembic resolves the SQLite URL built from the test environment.
    sys.modules.pop("app.database", None)
    sys.modules.pop("app.models", None)

    # Bootstrap schema up to the legacy revision.
    command.upgrade(alembic_cfg, "b7e4d2f9c8a1")

    legacy_metadata = sa.MetaData()
    procedures = sa.Table(
        "procedures",
        legacy_metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("metadata", sa.JSON),
    )
    procedure_steps = sa.Table(
        "procedure_steps",
        legacy_metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("procedure_id", sa.String),
        sa.Column("key", sa.String(255)),
        sa.Column("title", sa.String(255)),
        sa.Column("prompt", sa.Text),
        sa.Column("slots", sa.JSON),
        sa.Column("metadata", sa.JSON),
        sa.Column("checklists", sa.JSON),
        sa.Column("position", sa.Integer),
    )
    procedure_runs = sa.Table(
        "procedure_runs",
        legacy_metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("procedure_id", sa.String),
        sa.Column("user_id", sa.String(255)),
        sa.Column("state", sa.String(50)),
        sa.Column("created_at", sa.DateTime),
        sa.Column("closed_at", sa.DateTime),
    )
    procedure_run_step_states = sa.Table(
        "procedure_run_step_states",
        legacy_metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String),
        sa.Column("step_key", sa.String(255)),
        sa.Column("payload", sa.JSON),
        sa.Column("committed_at", sa.DateTime),
    )

    procedure_id = "proc-legacy"
    step_one_id = "step-one"
    step_two_id = "step-two"
    run_id = "run-legacy"

    step_one_slots = [
        {
            "name": "email",
            "label": "Email",
            "type": "string",
            "required": True,
            "position": 0,
            "metadata": {"placeholder": "user@example.com"},
        },
        {
            "name": "age",
            "label": "Age",
            "type": "number",
            "required": False,
            "position": 1,
            "metadata": {},
        },
    ]
    step_two_slots = [
        {
            "name": "document",
            "label": "Document",
            "type": "string",
            "required": True,
            "position": 0,
            "metadata": {"accept": ["pdf", "jpeg"]},
        }
    ]

    step_one_checklists = [
        {
            "key": "consent",
            "label": "Consent collected",
            "description": "User acknowledged terms",
            "required": True,
            "position": 0,
        },
        {
            "key": "double_check",
            "label": "Double check",
            "description": None,
            "required": False,
            "position": 1,
        },
    ]

    committed_at_step_one = datetime(2025, 2, 1, 12, 0, 0)
    committed_at_step_two = datetime(2025, 2, 2, 8, 30, 0)

    with sa.create_engine(database_url, future=True).begin() as conn:
        conn.execute(
            procedures.insert(),
            [
                {
                    "id": procedure_id,
                    "name": "Legacy Onboarding",
                    "description": "Legacy flow",
                    "metadata": {},
                }
            ],
        )
        conn.execute(
            procedure_steps.insert(),
            [
                {
                    "id": step_one_id,
                    "procedure_id": procedure_id,
                    "key": "profile",
                    "title": "Profile",
                    "prompt": "Collect profile data",
                    "slots": step_one_slots,
                    "metadata": {},
                    "checklists": step_one_checklists,
                    "position": 0,
                },
                {
                    "id": step_two_id,
                    "procedure_id": procedure_id,
                    "key": "verification",
                    "title": "Verification",
                    "prompt": "Verify identity",
                    "slots": step_two_slots,
                    "metadata": {},
                    "checklists": [],
                    "position": 1,
                },
            ],
        )
        conn.execute(
            procedure_runs.insert(),
            [
                {
                    "id": run_id,
                    "procedure_id": procedure_id,
                    "user_id": "user-123",
                    "state": "completed",
                    "created_at": datetime(2025, 2, 1, 11, 0, 0),
                    "closed_at": datetime(2025, 2, 2, 9, 0, 0),
                }
            ],
        )
        conn.execute(
            procedure_run_step_states.insert(),
            [
                {
                    "id": "state-profile",
                    "run_id": run_id,
                    "step_key": "profile",
                    "payload": {
                        "slots": {"email": "user@example.com", "age": 38},
                        "checklist": [
                            {
                                "key": "consent",
                                "label": "Consent collected",
                                "completed": True,
                                "completed_at": "2025-02-01T12:05:00",
                            },
                            {
                                "key": "double_check",
                                "label": "Double check",
                                "completed": False,
                                "completed_at": None,
                            },
                        ],
                    },
                    "committed_at": committed_at_step_one,
                },
                {
                    "id": "state-verification",
                    "run_id": run_id,
                    "step_key": "verification",
                    "payload": {
                        "slots": {"document": "passport.pdf"},
                        "checklist": [],
                    },
                    "committed_at": committed_at_step_two,
                },
            ],
        )

    # Upgrade to the normalized schema and validate the migrated data.
    command.upgrade(alembic_cfg, "head")

    normalized_metadata = sa.MetaData()
    procedure_slots = sa.Table(
        "procedure_slots",
        normalized_metadata,
        sa.Column("id", sa.String),
        sa.Column("step_id", sa.String),
        sa.Column("name", sa.String(255)),
        sa.Column("label", sa.String(255)),
        sa.Column("type", sa.String(50)),
        sa.Column("required", sa.Boolean),
        sa.Column("position", sa.Integer),
        sa.Column("configuration", sa.JSON),
    )
    procedure_step_checklist_items = sa.Table(
        "procedure_step_checklist_items",
        normalized_metadata,
        sa.Column("id", sa.String),
        sa.Column("step_id", sa.String),
        sa.Column("key", sa.String(255)),
        sa.Column("label", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("required", sa.Boolean),
        sa.Column("position", sa.Integer),
    )
    procedure_run_slot_values = sa.Table(
        "procedure_run_slot_values",
        normalized_metadata,
        sa.Column("id", sa.String),
        sa.Column("run_id", sa.String),
        sa.Column("slot_id", sa.String),
        sa.Column("value", sa.JSON),
        sa.Column("captured_at", sa.DateTime),
    )
    procedure_run_checklist_states = sa.Table(
        "procedure_run_checklist_item_states",
        normalized_metadata,
        sa.Column("id", sa.String),
        sa.Column("run_id", sa.String),
        sa.Column("checklist_item_id", sa.String),
        sa.Column("is_completed", sa.Boolean),
        sa.Column("completed_at", sa.DateTime),
    )

    with sa.create_engine(database_url, future=True).begin() as conn:
        slot_rows = conn.execute(
            sa.select(
                procedure_slots.c.step_id,
                procedure_slots.c.name,
                procedure_slots.c.label,
                procedure_slots.c.type,
                procedure_slots.c.required,
                procedure_slots.c.position,
                procedure_slots.c.configuration,
            )
        ).mappings()
        slots_by_step = {}
        for row in slot_rows:
            slots_by_step.setdefault(row["step_id"], []).append(
                {
                    "name": row["name"],
                    "label": row["label"],
                    "type": row["type"],
                    "required": bool(row["required"]),
                    "position": row["position"],
                    "metadata": row["configuration"],
                }
            )
        for items in slots_by_step.values():
            items.sort(key=lambda item: item["position"])
        assert slots_by_step[step_one_id] == step_one_slots
        assert slots_by_step[step_two_id] == step_two_slots

        checklist_rows = conn.execute(
            sa.select(
                procedure_step_checklist_items.c.step_id,
                procedure_step_checklist_items.c.key,
                procedure_step_checklist_items.c.label,
                procedure_step_checklist_items.c.description,
                procedure_step_checklist_items.c.required,
                procedure_step_checklist_items.c.position,
            )
        ).mappings()
        checklists_by_step = {}
        for row in checklist_rows:
            checklists_by_step.setdefault(row["step_id"], []).append(
                {
                    "key": row["key"],
                    "label": row["label"],
                    "description": row["description"],
                    "required": bool(row["required"]),
                    "position": row["position"],
                }
            )
        for items in checklists_by_step.values():
            items.sort(key=lambda item: item["position"])
        assert checklists_by_step[step_one_id] == step_one_checklists
        assert step_two_id not in checklists_by_step

        slot_values = conn.execute(
            sa.select(
                procedure_run_slot_values.c.run_id,
                procedure_slots.c.name,
                procedure_run_slot_values.c.value,
                procedure_run_slot_values.c.captured_at,
            ).join(
                procedure_slots,
                procedure_run_slot_values.c.slot_id == procedure_slots.c.id,
            )
        ).mappings()
        slot_value_map = {
            (row["run_id"], row["name"]): {
                "value": row["value"],
                "captured_at": row["captured_at"],
            }
            for row in slot_values
        }
        assert slot_value_map[(run_id, "email")]["value"] == "user@example.com"
        assert slot_value_map[(run_id, "age")]["value"] == 38
        assert slot_value_map[(run_id, "document")]["value"] == "passport.pdf"
        assert slot_value_map[(run_id, "email")]["captured_at"] == committed_at_step_one
        assert slot_value_map[(run_id, "document")]["captured_at"] == committed_at_step_two

        checklist_states = conn.execute(
            sa.select(
                procedure_run_checklist_states.c.run_id,
                procedure_step_checklist_items.c.key,
                procedure_run_checklist_states.c.is_completed,
                procedure_run_checklist_states.c.completed_at,
            ).join(
                procedure_step_checklist_items,
                procedure_run_checklist_states.c.checklist_item_id
                == procedure_step_checklist_items.c.id,
            )
        ).mappings()
        checklist_state_map = {
            (row["run_id"], row["key"]): {
                "completed": bool(row["is_completed"]),
                "completed_at": row["completed_at"],
            }
            for row in checklist_states
        }
        assert checklist_state_map[(run_id, "consent")] == {
            "completed": True,
            "completed_at": datetime.fromisoformat("2025-02-01T12:05:00"),
        }
        assert checklist_state_map[(run_id, "double_check")] == {
            "completed": False,
            "completed_at": None,
        }

    # Downgrade back to the legacy schema and verify that JSON payloads are restored.
    command.downgrade(alembic_cfg, "b7e4d2f9c8a1")

    with sa.create_engine(database_url, future=True).begin() as conn:
        step_payloads = conn.execute(
            sa.select(
                procedure_steps.c.id,
                procedure_steps.c.slots,
                procedure_steps.c.checklists,
            )
        ).mappings()
        payload_map = {row["id"]: row for row in step_payloads}
        assert payload_map[step_one_id]["slots"] == step_one_slots
        assert payload_map[step_one_id]["checklists"] == step_one_checklists
        assert payload_map[step_two_id]["slots"] == step_two_slots
        assert payload_map[step_two_id]["checklists"] == []
