"""add table for webrtc signaling sessions

Revision ID: b7e4d2f9c8a1
Revises: a3b2c1d4e5f6
Create Date: 2025-01-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e4d2f9c8a1"
down_revision: Union[str, Sequence[str], None] = "a3b2c1d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webrtc_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("responder_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("offer_sdp", sa.Text(), nullable=False),
        sa.Column("answer_sdp", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("responder_metadata", sa.JSON(), nullable=False),
        sa.Column("ice_candidates", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webrtc_sessions_status",
        "webrtc_sessions",
        ["status"],
    )
    op.create_index(
        "ix_webrtc_sessions_client",
        "webrtc_sessions",
        ["client_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_webrtc_sessions_client", table_name="webrtc_sessions")
    op.drop_index("ix_webrtc_sessions_status", table_name="webrtc_sessions")
    op.drop_table("webrtc_sessions")
