"""Add reliable quiz session deadlines.

Revision ID: 20260908_0002
Revises: 20260905_0001
Create Date: 2026-09-08
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260908_0002"
down_revision: str | None = "20260905_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_sessions",
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_quiz_sessions_deadline_at",
        "quiz_sessions",
        ["deadline_at"],
        unique=False,
    )
    op.execute(
        """
        UPDATE quiz_sessions
        SET deadline_at = finished_at,
            finished_at = NULL
        WHERE status = 'running'
          AND finished_at IS NOT NULL
        """
    )
    op.alter_column(
        "quiz_attempts",
        "finished_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )
    op.execute(
        """
        UPDATE quiz_attempts
        SET finished_at = NULL
        WHERE finished = false
        """
    )


def downgrade() -> None:
    op.drop_index("ix_quiz_sessions_deadline_at", table_name="quiz_sessions")
    op.drop_column("quiz_sessions", "deadline_at")
    op.alter_column(
        "quiz_attempts",
        "finished_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=sa.text("now()"),
    )
