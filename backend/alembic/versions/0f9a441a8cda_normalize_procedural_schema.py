"""normalize procedural schema

Revision ID: 0f9a441a8cda
Revises: b7e4d2f9c8a1
Create Date: 2025-10-14 10:15:36.016757

"""
from __future__ import annotations

import uuid
from typing import Iterable, List, Mapping, MutableMapping, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '0f9a441a8cda'
down_revision: Union[str, Sequence[str], None] = 'b7e4d2f9c8a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalised = value.strip().lower()
        return normalised in {"true", "t", "1", "yes", "y"}
    return default


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _coerce_dict(value: object) -> MutableMapping[str, object]:
    if isinstance(value, MutableMapping):
        return dict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _normalise_slots(step_id: str, raw_slots: object) -> List[dict[str, object]]:
    slots: List[dict[str, object]] = []
    if not isinstance(raw_slots, Iterable) or isinstance(raw_slots, (str, bytes)):
        return slots

    for index, raw_slot in enumerate(raw_slots):
        if not isinstance(raw_slot, Mapping):
            continue

        name = raw_slot.get("name")
        if not isinstance(name, str) or not name:
            continue

        slot_id = raw_slot.get("id")
        if isinstance(slot_id, bytes):
            slot_id = slot_id.decode()
        if not isinstance(slot_id, str) or not slot_id:
            slot_id = str(uuid.uuid4())

        label = raw_slot.get("label")
        if isinstance(label, (int, float)):
            label = str(label)
        if not isinstance(label, str):
            label = None

        raw_type = raw_slot.get("type") or raw_slot.get("slot_type") or "string"
        if isinstance(raw_type, bytes):
            raw_type = raw_type.decode()
        slot_type = str(raw_type)

        required = _coerce_bool(raw_slot.get("required", True), True)
        position = _coerce_int(raw_slot.get("position"), index)
        configuration = _coerce_dict(raw_slot.get("metadata") or raw_slot.get("configuration"))

        slots.append(
            {
                "id": slot_id,
                "step_id": step_id,
                "name": name,
                "label": label,
                "type": slot_type,
                "required": required,
                "position": position,
                "configuration": configuration,
            }
        )

    return slots


def _normalise_checklists(step_id: str, raw_items: object) -> List[dict[str, object]]:
    items: List[dict[str, object]] = []
    if not isinstance(raw_items, Iterable) or isinstance(raw_items, (str, bytes)):
        return items

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            continue

        key = raw_item.get("key") or raw_item.get("name")
        if not isinstance(key, str) or not key:
            continue

        item_id = raw_item.get("id")
        if isinstance(item_id, bytes):
            item_id = item_id.decode()
        if not isinstance(item_id, str) or not item_id:
            item_id = str(uuid.uuid4())

        label = raw_item.get("label")
        if isinstance(label, (int, float)):
            label = str(label)
        if not isinstance(label, str) or not label:
            label = key

        description = raw_item.get("description")
        if isinstance(description, (int, float)):
            description = str(description)
        if not isinstance(description, str):
            description = None

        required = _coerce_bool(raw_item.get("required", False), False)
        position = _coerce_int(raw_item.get("position"), index)

        items.append(
            {
                "id": item_id,
                "step_id": step_id,
                "key": key,
                "label": label,
                "description": description,
                "required": required,
                "position": position,
            }
        )

    return items


def _migrate_legacy_step_data(connection: sa.Connection) -> None:
    procedure_steps = sa.table(
        "procedure_steps",
        sa.column("id", sa.String()),
        sa.column("slots", sa.JSON()),
        sa.column("checklists", sa.JSON()),
    )
    legacy_steps = connection.execute(
        sa.select(procedure_steps.c.id, procedure_steps.c.slots, procedure_steps.c.checklists)
    ).all()

    slot_rows: List[dict[str, object]] = []
    checklist_rows: List[dict[str, object]] = []

    for step_id, raw_slots, raw_checklists in legacy_steps:
        slot_rows.extend(_normalise_slots(step_id, raw_slots))
        checklist_rows.extend(_normalise_checklists(step_id, raw_checklists))

    if slot_rows:
        procedure_slots = sa.table(
            "procedure_slots",
            sa.column("id", sa.String()),
            sa.column("step_id", sa.String()),
            sa.column("name", sa.String()),
            sa.column("label", sa.String()),
            sa.column("type", sa.String()),
            sa.column("required", sa.Boolean()),
            sa.column("position", sa.Integer()),
            sa.column("configuration", sa.JSON()),
        )
        op.bulk_insert(procedure_slots, slot_rows)

    if checklist_rows:
        checklist_items = sa.table(
            "procedure_step_checklist_items",
            sa.column("id", sa.String()),
            sa.column("step_id", sa.String()),
            sa.column("key", sa.String()),
            sa.column("label", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("required", sa.Boolean()),
            sa.column("position", sa.Integer()),
        )
        op.bulk_insert(checklist_items, checklist_rows)


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('procedure_slots',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('step_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=True),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('required', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('configuration', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['step_id'], ['procedure_steps.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('step_id', 'name', name='uq_procedure_slot_name')
    )
    op.create_table('procedure_step_checklist_items',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('step_id', sa.String(), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('required', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['step_id'], ['procedure_steps.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('step_id', 'key', name='uq_procedure_step_checklist_key')
    )
    op.create_table('procedure_run_checklist_item_states',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('run_id', sa.String(), nullable=False),
    sa.Column('checklist_item_id', sa.String(), nullable=False),
    sa.Column('is_completed', sa.Boolean(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['checklist_item_id'], ['procedure_step_checklist_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['procedure_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'checklist_item_id', name='uq_procedure_run_checklist_item_state')
    )
    op.create_table('procedure_run_slot_values',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('run_id', sa.String(), nullable=False),
    sa.Column('slot_id', sa.String(), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.Column('captured_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['procedure_runs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['slot_id'], ['procedure_slots.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'slot_id', name='uq_procedure_run_slot_value')
    )

    connection = op.get_bind()
    _migrate_legacy_step_data(connection)

    op.drop_column('procedure_steps', 'checklists')
    op.drop_column('procedure_steps', 'slots')
    # The existing WebRTC indexes are intentionally preserved.  They are managed
    # by previous migrations and are unrelated to this schema change, so avoid
    # dropping them during the upgrade.
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    # Matching the upgrade, the WebRTC indexes remain untouched by this
    # migration.  They continue to be provided by earlier revisions.
    op.add_column('procedure_steps', sa.Column('slots', sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column('procedure_steps', sa.Column('checklists', sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")))

    connection = op.get_bind()

    slots_table = sa.table(
        "procedure_slots",
        sa.column("id", sa.String()),
        sa.column("step_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("label", sa.String()),
        sa.column("type", sa.String()),
        sa.column("required", sa.Boolean()),
        sa.column("position", sa.Integer()),
        sa.column("configuration", sa.JSON()),
    )
    checklist_table = sa.table(
        "procedure_step_checklist_items",
        sa.column("id", sa.String()),
        sa.column("step_id", sa.String()),
        sa.column("key", sa.String()),
        sa.column("label", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("required", sa.Boolean()),
        sa.column("position", sa.Integer()),
    )
    steps_table = sa.table(
        "procedure_steps",
        sa.column("id", sa.String()),
        sa.column("slots", sa.JSON()),
        sa.column("checklists", sa.JSON()),
    )

    legacy_slots = connection.execute(
        sa.select(
            slots_table.c.step_id,
            slots_table.c.id,
            slots_table.c.name,
            slots_table.c.label,
            slots_table.c.type,
            slots_table.c.required,
            slots_table.c.position,
            slots_table.c.configuration,
        )
    ).mappings()

    slots_by_step: dict[str, List[dict[str, object]]] = {}
    for row in legacy_slots:
        configuration = row["configuration"] or {}
        if not isinstance(configuration, Mapping):
            configuration = {}
        slot_payload = {
            "id": row["id"],
            "name": row["name"],
            "label": row["label"],
            "type": row["type"],
            "required": bool(row["required"]),
            "position": row["position"],
            "metadata": dict(configuration),
        }
        slots_by_step.setdefault(row["step_id"], []).append(slot_payload)

    for payloads in slots_by_step.values():
        payloads.sort(key=lambda item: (item.get("position", 0), item.get("name", "")))

    legacy_checklists = connection.execute(
        sa.select(
            checklist_table.c.step_id,
            checklist_table.c.id,
            checklist_table.c.key,
            checklist_table.c.label,
            checklist_table.c.description,
            checklist_table.c.required,
            checklist_table.c.position,
        )
    ).mappings()

    checklists_by_step: dict[str, List[dict[str, object]]] = {}
    for row in legacy_checklists:
        item_payload = {
            "id": row["id"],
            "key": row["key"],
            "label": row["label"],
            "description": row["description"],
            "required": bool(row["required"]),
            "position": row["position"],
        }
        checklists_by_step.setdefault(row["step_id"], []).append(item_payload)

    for payloads in checklists_by_step.values():
        payloads.sort(key=lambda item: (item.get("position", 0), item.get("key", "")))

    step_ids = connection.execute(sa.select(steps_table.c.id)).scalars().all()
    for step_id in step_ids:
        connection.execute(
            steps_table.update()
            .where(steps_table.c.id == step_id)
            .values(
                slots=slots_by_step.get(step_id, []),
                checklists=checklists_by_step.get(step_id, []),
            )
        )

    op.alter_column('procedure_steps', 'slots', server_default=None)
    op.alter_column('procedure_steps', 'checklists', server_default=None)

    op.drop_table('procedure_run_slot_values')
    op.drop_table('procedure_run_checklist_item_states')
    op.drop_table('procedure_step_checklist_items')
    op.drop_table('procedure_slots')
    # ### end Alembic commands ###
