"""normalize procedural data model

Revision ID: c6f7d8a9b0c1
Revises: b7e4d2f9c8a1
Create Date: 2025-02-12 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Mapping, Sequence, Union

import sqlalchemy as sa

from alembic import op


def _generate_uuid() -> str:
    """Return a string UUID compatible with existing tables."""

    return str(uuid.uuid4())


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _coerce_sequence(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result: list[Mapping[str, Any]] = []
        for item in value:
            if isinstance(item, Mapping):
                result.append(item)
        return result
    return []


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


_pre_normalized_procedure_steps = sa.Table(
    "procedure_steps",
    sa.MetaData(),
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("procedure_id", sa.String(), nullable=False),
    sa.Column("key", sa.String(length=255), nullable=False),
    sa.Column("title", sa.String(length=255), nullable=False),
    sa.Column("prompt", sa.Text(), nullable=False),
    sa.Column("slots", sa.JSON(), nullable=False),
    sa.Column("metadata", sa.JSON(), nullable=False),
    sa.Column("checklists", sa.JSON(), nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
)

_post_normalized_procedure_steps = sa.Table(
    "procedure_steps",
    sa.MetaData(),
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("procedure_id", sa.String(), nullable=False),
    sa.Column("key", sa.String(length=255), nullable=False),
    sa.Column("title", sa.String(length=255), nullable=False),
    sa.Column("prompt", sa.Text(), nullable=True),
    sa.Column("metadata", sa.JSON(), nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
)

_procedure_slots_table = sa.Table(
    "procedure_slots",
    sa.MetaData(),
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("step_id", sa.String(), nullable=False),
    sa.Column("name", sa.String(length=255), nullable=False),
    sa.Column("label", sa.String(length=255), nullable=True),
    sa.Column("type", sa.String(length=50), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("required", sa.Boolean(), nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("validate", sa.String(length=255), nullable=True),
    sa.Column("mask", sa.String(length=255), nullable=True),
    sa.Column("options", sa.JSON(), nullable=False),
    sa.Column("metadata", sa.JSON(), nullable=False),
)

_procedure_step_checklist_items_table = sa.Table(
    "procedure_step_checklist_items",
    sa.MetaData(),
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("step_id", sa.String(), nullable=False),
    sa.Column("key", sa.String(length=255), nullable=False),
    sa.Column("label", sa.String(length=255), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("required", sa.Boolean(), nullable=False),
    sa.Column("default_state", sa.Boolean(), nullable=True),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("metadata", sa.JSON(), nullable=False),
)

_procedure_runs_table = sa.Table(
    "procedure_runs",
    sa.MetaData(),
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("procedure_id", sa.String(), nullable=False),
)

_procedure_run_step_states_table = sa.Table(
    "procedure_run_step_states",
    sa.MetaData(),
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("run_id", sa.String(), nullable=False),
    sa.Column("step_key", sa.String(length=255), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("committed_at", sa.DateTime(), nullable=False),
)

_procedure_run_slot_values_table = sa.Table(
    "procedure_run_slot_values",
    sa.MetaData(),
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("run_id", sa.String(), nullable=False),
    sa.Column("slot_id", sa.String(), nullable=False),
    sa.Column("value", sa.JSON(), nullable=True),
    sa.Column("captured_at", sa.DateTime(), nullable=False),
)

_procedure_run_checklist_states_table = sa.Table(
    "procedure_run_checklist_item_states",
    sa.MetaData(),
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("run_id", sa.String(), nullable=False),
    sa.Column("checklist_item_id", sa.String(), nullable=False),
    sa.Column("is_completed", sa.Boolean(), nullable=False),
    sa.Column("completed_at", sa.DateTime(), nullable=True),
)


# revision identifiers, used by Alembic.
revision: str = "c6f7d8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "b7e4d2f9c8a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the normalized procedural schema aligned with SQLAlchemy models."""

    bind = op.get_bind()

    step_rows = bind.execute(
        sa.select(
            _pre_normalized_procedure_steps.c.id,
            _pre_normalized_procedure_steps.c.procedure_id,
            _pre_normalized_procedure_steps.c.key,
            _pre_normalized_procedure_steps.c.slots,
            _pre_normalized_procedure_steps.c.checklists,
        )
    ).mappings()

    step_key_map: dict[tuple[str, str], str] = {}
    slot_lookup: dict[tuple[str, str], str] = {}
    checklist_lookup: dict[tuple[str, str], str] = {}
    slot_inserts: list[dict[str, Any]] = []
    checklist_inserts: list[dict[str, Any]] = []

    for row in step_rows:
        step_id = row["id"]
        procedure_id = row["procedure_id"]
        step_key = row["key"]
        step_key_map[(procedure_id, step_key)] = step_id

        slots = _coerce_sequence(row.get("slots"))
        for index, slot_payload in enumerate(slots):
            name = slot_payload.get("name")
            if not isinstance(name, str) or not name:
                continue
            slot_id = _generate_uuid()
            required = slot_payload.get("required")
            if not isinstance(required, bool):
                required = bool(required) if required is not None else True
            position = slot_payload.get("position")
            if not isinstance(position, int):
                position = index
            configuration = _coerce_mapping(slot_payload.get("metadata"))
            description = slot_payload.get("description")
            if not isinstance(description, str):
                description_candidate = configuration.get("description")
                description = (
                    description_candidate
                    if isinstance(description_candidate, str)
                    else None
                )
            validate = slot_payload.get("validate")
            if not isinstance(validate, str):
                validate_candidate = configuration.get("validate")
                validate = (
                    validate_candidate if isinstance(validate_candidate, str) else None
                )
            mask = slot_payload.get("mask")
            if not isinstance(mask, str):
                mask_candidate = configuration.get("mask")
                mask = mask_candidate if isinstance(mask_candidate, str) else None
            raw_options = slot_payload.get("options")
            if not isinstance(raw_options, Sequence) or isinstance(raw_options, (str, bytes)):
                raw_options = configuration.get("options")
            options: list[str] = []
            if isinstance(raw_options, Sequence) and not isinstance(
                raw_options, (str, bytes)
            ):
                for option in raw_options:
                    if isinstance(option, str):
                        options.append(option)

            metadata = dict(configuration)
            metadata.pop("description", None)
            metadata.pop("validate", None)
            metadata.pop("mask", None)
            metadata.pop("options", None)

            slot_inserts.append(
                {
                    "id": slot_id,
                    "step_id": step_id,
                    "name": name,
                    "label": slot_payload.get("label"),
                    "type": slot_payload.get("type", "string"),
                    "required": required,
                    "position": position,
                    "description": description,
                    "validate": validate,
                    "mask": mask,
                    "options": options,
                    "metadata": metadata,
                }
            )
            slot_lookup[(step_id, name)] = slot_id

        checklists = _coerce_sequence(row.get("checklists"))
        for index, checklist_payload in enumerate(checklists):
            key = checklist_payload.get("key")
            if not isinstance(key, str) or not key:
                continue
            checklist_id = _generate_uuid()
            required = checklist_payload.get("required")
            if not isinstance(required, bool):
                required = bool(required) if required is not None else False
            position = checklist_payload.get("position")
            if not isinstance(position, int):
                position = index
            checklist_metadata = _coerce_mapping(checklist_payload.get("metadata"))
            default_state = checklist_payload.get("default_state")
            if not isinstance(default_state, bool) and default_state is not None:
                default_state = (
                    checklist_metadata.get("default_state")
                    if isinstance(checklist_metadata.get("default_state"), bool)
                    else bool(default_state)
                )
            elif default_state is None:
                default_state_candidate = checklist_metadata.get("default_state")
                default_state = (
                    default_state_candidate
                    if isinstance(default_state_candidate, bool)
                    else None
                )

            metadata = dict(checklist_metadata)
            metadata.pop("default_state", None)

            checklist_inserts.append(
                {
                    "id": checklist_id,
                    "step_id": step_id,
                    "key": key,
                    "label": checklist_payload.get("label", key),
                    "description": checklist_payload.get("description"),
                    "required": required,
                    "default_state": default_state,
                    "position": position,
                    "metadata": metadata,
                }
            )
            checklist_lookup[(step_id, key)] = checklist_id

    run_procedures = bind.execute(
        sa.select(
            _procedure_runs_table.c.id,
            _procedure_runs_table.c.procedure_id,
        )
    ).mappings()
    run_procedure_map = {row["id"]: row["procedure_id"] for row in run_procedures}

    step_state_rows = list(
        bind.execute(
            sa.select(
                _procedure_run_step_states_table.c.run_id,
                _procedure_run_step_states_table.c.step_key,
                _procedure_run_step_states_table.c.payload,
                _procedure_run_step_states_table.c.committed_at,
            )
        ).mappings()
    )

    with op.batch_alter_table("procedures", schema=None) as batch_op:
        batch_op.alter_column("description", existing_type=sa.Text(), nullable=True)

    with op.batch_alter_table(
        "procedure_steps", schema=None, copy_from=_pre_normalized_procedure_steps
    ) as batch_op:
        batch_op.alter_column("prompt", existing_type=sa.Text(), nullable=True)
        batch_op.drop_column("slots")
        batch_op.drop_column("checklists")
        batch_op.create_foreign_key(
            "fk_procedure_steps_procedure_id",
            "procedures",
            ["procedure_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_procedure_step_key",
            ["procedure_id", "key"],
        )

    op.create_table(
        "procedure_slots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("validate", sa.String(length=255), nullable=True),
        sa.Column("mask", sa.String(length=255), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["step_id"], ["procedure_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id", "name", name="uq_procedure_slot_name"),
    )
    op.create_index(
        "ix_procedure_slots_step_id",
        "procedure_slots",
        ["step_id"],
    )

    op.create_table(
        "procedure_step_checklist_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("default_state", sa.Boolean(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["step_id"], ["procedure_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id", "key", name="uq_procedure_step_checklist_key"),
    )
    op.create_index(
        "ix_procedure_step_checklist_items_step_id",
        "procedure_step_checklist_items",
        ["step_id"],
    )

    op.create_table(
        "procedure_run_slot_values",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("slot_id", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["procedure_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slot_id"], ["procedure_slots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "slot_id", name="uq_procedure_run_slot_value"),
    )
    op.create_index(
        "ix_procedure_run_slot_values_run_id",
        "procedure_run_slot_values",
        ["run_id"],
    )
    op.create_index(
        "ix_procedure_run_slot_values_slot_id",
        "procedure_run_slot_values",
        ["slot_id"],
    )

    op.create_table(
        "procedure_run_checklist_item_states",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("checklist_item_id", sa.String(), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["procedure_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["checklist_item_id"],
            ["procedure_step_checklist_items.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "checklist_item_id",
            name="uq_procedure_run_checklist_item_state",
        ),
    )
    op.create_index(
        "ix_procedure_run_checklist_item_states_run_id",
        "procedure_run_checklist_item_states",
        ["run_id"],
    )
    op.create_index(
        "ix_procedure_run_checklist_item_states_item_id",
        "procedure_run_checklist_item_states",
        ["checklist_item_id"],
    )

    if slot_inserts:
        op.bulk_insert(_procedure_slots_table, slot_inserts)

    if checklist_inserts:
        op.bulk_insert(_procedure_step_checklist_items_table, checklist_inserts)

    slot_value_inserts: list[dict[str, Any]] = []
    checklist_state_inserts: list[dict[str, Any]] = []

    for state in step_state_rows:
        run_id = state["run_id"]
        procedure_id = run_procedure_map.get(run_id)
        if not procedure_id:
            continue
        step_id = step_key_map.get((procedure_id, state["step_key"]))
        if not step_id:
            continue

        payload = _coerce_mapping(state.get("payload"))
        committed_at = _coerce_datetime(state.get("committed_at"))
        if committed_at is None:
            committed_at = datetime.utcnow()

        slot_payload = _coerce_mapping(payload.get("slots"))
        for name, value in slot_payload.items():
            slot_id = slot_lookup.get((step_id, name))
            if not slot_id:
                continue
            slot_value_inserts.append(
                {
                    "id": _generate_uuid(),
                    "run_id": run_id,
                    "slot_id": slot_id,
                    "value": value,
                    "captured_at": committed_at,
                }
            )

        checklist_payload = _coerce_sequence(payload.get("checklist"))
        for item in checklist_payload:
            key = item.get("key")
            if not isinstance(key, str) or not key:
                continue
            checklist_id = checklist_lookup.get((step_id, key))
            if not checklist_id:
                continue
            completed = item.get("completed")
            if not isinstance(completed, bool):
                completed = bool(completed)
            completed_at = _coerce_datetime(item.get("completed_at"))
            if not completed:
                completed_at = None
            checklist_state_inserts.append(
                {
                    "id": _generate_uuid(),
                    "run_id": run_id,
                    "checklist_item_id": checklist_id,
                    "is_completed": completed,
                    "completed_at": completed_at,
                }
            )

    if slot_value_inserts:
        op.bulk_insert(_procedure_run_slot_values_table, slot_value_inserts)

    if checklist_state_inserts:
        op.bulk_insert(_procedure_run_checklist_states_table, checklist_state_inserts)


def downgrade() -> None:
    """Rollback the normalized procedural schema."""

    bind = op.get_bind()

    with op.batch_alter_table("procedures", schema=None) as batch_op:
        batch_op.alter_column("description", existing_type=sa.Text(), nullable=False)

    with op.batch_alter_table(
        "procedure_steps", schema=None, copy_from=_post_normalized_procedure_steps
    ) as batch_op:
        batch_op.alter_column("prompt", existing_type=sa.Text(), nullable=False)
        batch_op.add_column(
            sa.Column(
                "checklists",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "slots",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )

    slot_rows = bind.execute(
        sa.select(
            _procedure_slots_table.c.step_id,
            _procedure_slots_table.c.name,
            _procedure_slots_table.c.label,
            _procedure_slots_table.c.type,
            _procedure_slots_table.c.description,
            _procedure_slots_table.c.required,
            _procedure_slots_table.c.position,
            _procedure_slots_table.c.validate,
            _procedure_slots_table.c.mask,
            _procedure_slots_table.c.options,
            _procedure_slots_table.c.metadata,
        )
    ).mappings()

    slots_by_step: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in slot_rows:
        configuration = _coerce_mapping(row.get("metadata"))
        description = row.get("description")
        if isinstance(description, str):
            configuration.setdefault("description", description)
        validate = row.get("validate")
        if isinstance(validate, str):
            configuration.setdefault("validate", validate)
        mask = row.get("mask")
        if isinstance(mask, str):
            configuration.setdefault("mask", mask)
        options = row.get("options")
        if isinstance(options, Sequence) and not isinstance(options, (str, bytes)):
            configuration.setdefault("options", [str(option) for option in options])

        slots_by_step[row["step_id"]].append(
            {
                "name": row["name"],
                "label": row["label"],
                "type": row["type"],
                "required": bool(row["required"]),
                "position": row["position"],
                "metadata": dict(configuration),
            }
        )

    for values in slots_by_step.values():
        values.sort(key=lambda item: item.get("position", 0))

    checklist_rows = bind.execute(
        sa.select(
            _procedure_step_checklist_items_table.c.step_id,
            _procedure_step_checklist_items_table.c.key,
            _procedure_step_checklist_items_table.c.label,
            _procedure_step_checklist_items_table.c.description,
            _procedure_step_checklist_items_table.c.required,
            _procedure_step_checklist_items_table.c.default_state,
            _procedure_step_checklist_items_table.c.position,
            _procedure_step_checklist_items_table.c.metadata,
        )
    ).mappings()

    checklists_by_step: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in checklist_rows:
        metadata = _coerce_mapping(row.get("metadata"))
        default_state = row.get("default_state")
        if isinstance(default_state, bool):
            metadata.setdefault("default_state", default_state)
        checklists_by_step[row["step_id"]].append(
            {
                "key": row["key"],
                "label": row["label"],
                "description": row["description"],
                "required": bool(row["required"]),
                "position": row["position"],
                "metadata": dict(metadata),
            }
        )

    for values in checklists_by_step.values():
        values.sort(key=lambda item: item.get("position", 0))

    step_ids = bind.execute(sa.select(_pre_normalized_procedure_steps.c.id)).scalars()

    for step_id in step_ids:
        bind.execute(
            sa.update(_pre_normalized_procedure_steps)
            .where(_pre_normalized_procedure_steps.c.id == step_id)
            .values(
                slots=slots_by_step.get(step_id, []),
                checklists=checklists_by_step.get(step_id, []),
            )
        )

    op.drop_index(
        "ix_procedure_run_checklist_item_states_item_id",
        table_name="procedure_run_checklist_item_states",
    )
    op.drop_index(
        "ix_procedure_run_checklist_item_states_run_id",
        table_name="procedure_run_checklist_item_states",
    )
    op.drop_table("procedure_run_checklist_item_states")

    op.drop_index(
        "ix_procedure_run_slot_values_slot_id",
        table_name="procedure_run_slot_values",
    )
    op.drop_index(
        "ix_procedure_run_slot_values_run_id",
        table_name="procedure_run_slot_values",
    )
    op.drop_table("procedure_run_slot_values")

    op.drop_index(
        "ix_procedure_step_checklist_items_step_id",
        table_name="procedure_step_checklist_items",
    )
    op.drop_table("procedure_step_checklist_items")

    op.drop_index(
        "ix_procedure_slots_step_id",
        table_name="procedure_slots",
    )
    op.drop_table("procedure_slots")

    with op.batch_alter_table(
        "procedure_steps", schema=None, copy_from=_pre_normalized_procedure_steps
    ) as batch_op:
        batch_op.alter_column("checklists", server_default=None)
        batch_op.alter_column("slots", server_default=None)
