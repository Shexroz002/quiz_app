"""Remembered Telegram channels for the bot's channel quizzes.

One table and nothing else: the channels an admin has already bound, so the
bot can offer a list instead of asking for a forwarded post every time. The
admin rights behind it are still verified on every publish, so a row here
grants nothing on its own.

Revision ID: 20261008_0009
Revises: 20261006_0008
Create Date: 2026-10-08
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_0009"
down_revision: str | None = "20261006_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "chat_id", name="uq_telegram_channel_owner"),
    )
    op.create_index("ix_telegram_channels_created_at", "telegram_channels", ["created_at"])
    op.create_index("ix_telegram_channels_updated_at", "telegram_channels", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_telegram_channels_updated_at", table_name="telegram_channels")
    op.drop_index("ix_telegram_channels_created_at", table_name="telegram_channels")
    op.drop_table("telegram_channels")
