"""normalize procedural data model

Revision ID: c6f7d8a9b0c1
Revises: b7e4d2f9c8a1
Create Date: 2025-02-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6f7d8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "b7e4d2f9c8a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the normalized procedural schema."""

    op.create_table(
        "procedure_step_slots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=50), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["step_id"], ["procedure_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id", "name", name="uq_procedure_step_slot_name"),
    )
    op.create_index(
        "ix_procedure_step_slots_step",
        "procedure_step_slots",
        ["step_id"],
    )

    op.create_table(
        "procedure_slot_options",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slot_id", sa.String(), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["slot_id"], ["procedure_step_slots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slot_id", "value", name="uq_procedure_slot_option"),
    )
    op.create_index(
        "ix_procedure_slot_options_slot",
        "procedure_slot_options",
        ["slot_id"],
    )

    op.create_table(
        "procedure_step_checklists",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["step_id"], ["procedure_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id", "title", name="uq_procedure_step_checklist_title"),
    )
    op.create_index(
        "ix_procedure_step_checklists_step",
        "procedure_step_checklists",
        ["step_id"],
    )

    op.create_table(
        "procedure_step_checklist_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("checklist_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["checklist_id"], ["procedure_step_checklists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checklist_id", "label", name="uq_procedure_checklist_item_label"),
    )
    op.create_index(
        "ix_procedure_step_checklist_items_checklist",
        "procedure_step_checklist_items",
        ["checklist_id"],
    )

    op.create_table(
        "procedure_run_steps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["procedure_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["procedure_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "step_id", name="uq_procedure_run_step"),
    )
    op.create_index(
        "ix_procedure_run_steps_run",
        "procedure_run_steps",
        ["run_id"],
    )
    op.create_index(
        "ix_procedure_run_steps_step",
        "procedure_run_steps",
        ["step_id"],
    )
    op.create_index(
        "ix_procedure_run_steps_status",
        "procedure_run_steps",
        ["status"],
    )

    op.create_table(
        "procedure_run_slot_values",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_step_id", sa.String(), nullable=False),
        sa.Column("slot_id", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["run_step_id"], ["procedure_run_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slot_id"], ["procedure_step_slots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_step_id", "slot_id", name="uq_procedure_run_slot_value"),
    )
    op.create_index(
        "ix_procedure_run_slot_values_step",
        "procedure_run_slot_values",
        ["run_step_id"],
    )
    op.create_index(
        "ix_procedure_run_slot_values_slot",
        "procedure_run_slot_values",
        ["slot_id"],
    )

    op.create_table(
        "procedure_run_checklist_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_step_id", sa.String(), nullable=False),
        sa.Column("checklist_item_id", sa.String(), nullable=False),
        sa.Column("is_checked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_step_id"], ["procedure_run_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["procedure_step_checklist_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_step_id", "checklist_item_id", name="uq_procedure_run_checklist_item"),
    )
    op.create_index(
        "ix_procedure_run_checklist_items_step",
        "procedure_run_checklist_items",
        ["run_step_id"],
    )
    op.create_index(
        "ix_procedure_run_checklist_items_item",
        "procedure_run_checklist_items",
        ["checklist_item_id"],
    )


def downgrade() -> None:
    """Rollback the normalized procedural schema."""

    op.drop_index(
        "ix_procedure_run_checklist_items_item",
        table_name="procedure_run_checklist_items",
    )
    op.drop_index(
        "ix_procedure_run_checklist_items_step",
        table_name="procedure_run_checklist_items",
    )
    op.drop_table("procedure_run_checklist_items")

    op.drop_index(
        "ix_procedure_run_slot_values_slot",
        table_name="procedure_run_slot_values",
    )
    op.drop_index(
        "ix_procedure_run_slot_values_step",
        table_name="procedure_run_slot_values",
    )
    op.drop_table("procedure_run_slot_values")

    op.drop_index("ix_procedure_run_steps_status", table_name="procedure_run_steps")
    op.drop_index("ix_procedure_run_steps_step", table_name="procedure_run_steps")
    op.drop_index("ix_procedure_run_steps_run", table_name="procedure_run_steps")
    op.drop_table("procedure_run_steps")

    op.drop_index(
        "ix_procedure_step_checklist_items_checklist",
        table_name="procedure_step_checklist_items",
    )
    op.drop_table("procedure_step_checklist_items")

    op.drop_index(
        "ix_procedure_step_checklists_step",
        table_name="procedure_step_checklists",
    )
    op.drop_table("procedure_step_checklists")

    op.drop_index("ix_procedure_slot_options_slot", table_name="procedure_slot_options")
    op.drop_table("procedure_slot_options")

    op.drop_index("ix_procedure_step_slots_step", table_name="procedure_step_slots")
    op.drop_table("procedure_step_slots")
