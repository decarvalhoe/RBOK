"""normalize procedural data model

Revision ID: c6f7d8a9b0c1
Revises: b7e4d2f9c8a1
Create Date: 2025-02-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


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
    sa.Column("prompt", sa.Text(), nullable=False),
    sa.Column("metadata", sa.JSON(), nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
)


# revision identifiers, used by Alembic.
revision: str = "c6f7d8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "b7e4d2f9c8a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the normalized procedural schema aligned with SQLAlchemy models."""

    with op.batch_alter_table(
        "procedure_steps", schema=None, copy_from=_pre_normalized_procedure_steps
    ) as batch_op:
        batch_op.drop_column("slots")
        batch_op.drop_column("checklists")

    op.create_table(
        "procedure_slots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("configuration", sa.JSON(), nullable=False),
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
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
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


def downgrade() -> None:
    """Rollback the normalized procedural schema."""

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
        "procedure_steps", schema=None, copy_from=_post_normalized_procedure_steps
    ) as batch_op:
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

    with op.batch_alter_table(
        "procedure_steps", schema=None, copy_from=_pre_normalized_procedure_steps
    ) as batch_op:
        batch_op.alter_column("checklists", server_default=None)
        batch_op.alter_column("slots", server_default=None)
