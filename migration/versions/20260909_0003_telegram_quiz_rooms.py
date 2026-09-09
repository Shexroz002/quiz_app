"""Add durable Telegram quiz rooms.

Revision ID: 20260909_0003
Revises: 20260908_0002
Create Date: 2026-09-09
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260909_0003"
down_revision: str | None = "20260908_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_quiz_rooms",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_username", sa.String(length=64), nullable=False),
        sa.Column("published_revision", sa.String(length=64), nullable=True),
        sa.Column("leaderboard_delivered_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["quiz_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "message_id", name="uq_telegram_room_message"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        "ix_telegram_quiz_rooms_created_at",
        "telegram_quiz_rooms",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_quiz_rooms_updated_at",
        "telegram_quiz_rooms",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_quiz_rooms_updated_at", table_name="telegram_quiz_rooms")
    op.drop_index("ix_telegram_quiz_rooms_created_at", table_name="telegram_quiz_rooms")
    op.drop_table("telegram_quiz_rooms")
