"""Remembered Telegram chats can be groups too, not only channels.

One column: the list a row belongs to. Existing rows are channels, which is
what the default says, so nothing else has to change.

Revision ID: 20261009_0010
Revises: 20261008_0009
Create Date: 2026-10-09
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261009_0010"
down_revision: str | None = "20261008_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telegram_channels",
        sa.Column("kind", sa.String(16), nullable=False, server_default="channel"),
    )


def downgrade() -> None:
    op.drop_column("telegram_channels", "kind")
