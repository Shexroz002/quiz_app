"""Add durable Telegram single-player result deliveries.

Revision ID: 20260909_0004
Revises: 20260909_0003
Create Date: 2026-09-09
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260909_0004"
down_revision: str | None = "20260909_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_single_player_result_deliveries",
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["quiz_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["quiz_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id"),
    )
    op.create_index(
        "ix_telegram_single_player_result_deliveries_created_at",
        "telegram_single_player_result_deliveries",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_single_player_result_deliveries_delivered_at",
        "telegram_single_player_result_deliveries",
        ["delivered_at"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_single_player_result_deliveries_session_id",
        "telegram_single_player_result_deliveries",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_single_player_result_deliveries_updated_at",
        "telegram_single_player_result_deliveries",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_single_player_result_deliveries_user_id",
        "telegram_single_player_result_deliveries",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_single_player_result_deliveries_user_id",
        table_name="telegram_single_player_result_deliveries",
    )
    op.drop_index(
        "ix_telegram_single_player_result_deliveries_updated_at",
        table_name="telegram_single_player_result_deliveries",
    )
    op.drop_index(
        "ix_telegram_single_player_result_deliveries_session_id",
        table_name="telegram_single_player_result_deliveries",
    )
    op.drop_index(
        "ix_telegram_single_player_result_deliveries_delivered_at",
        table_name="telegram_single_player_result_deliveries",
    )
    op.drop_index(
        "ix_telegram_single_player_result_deliveries_created_at",
        table_name="telegram_single_player_result_deliveries",
    )
    op.drop_table("telegram_single_player_result_deliveries")
