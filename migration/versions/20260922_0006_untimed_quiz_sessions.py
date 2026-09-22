"""Allow a quiz session to run without a time limit.

A single-player session started with no `duration_minute` gets a NULL duration
and, with it, a NULL `deadline_at`. The expiry sweep already skips sessions
whose `deadline_at` is NULL, so an untimed session simply never expires and the
student can come back to it.

Revision ID: 20260922_0006
Revises: 20260913_0005
Create Date: 2026-09-22
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260922_0006"
down_revision: str | None = "20260913_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "quiz_sessions",
        "duration_minutes",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Untimed sessions have no duration to restore, so they are given the
    # default the endpoint used to apply. Without this the column cannot go
    # back to NOT NULL.
    op.execute("UPDATE quiz_sessions SET duration_minutes = 30 WHERE duration_minutes IS NULL")
    op.alter_column(
        "quiz_sessions",
        "duration_minutes",
        existing_type=sa.Integer(),
        nullable=False,
    )
