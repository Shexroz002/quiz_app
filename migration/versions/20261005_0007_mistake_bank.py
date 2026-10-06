"""Mistake bank: per-question review state for a student.

The questions a student got wrong are already recorded in `attempt_answers`,
so this table stores only the review schedule — when the question comes back,
how many correct answers in a row it has, and whether it has been cleared.
That keeps the bank rebuildable from answers without losing progress, and lets
the service fill it from a student's existing history on first read.

Revision ID: 20261005_0007
Revises: 20260922_0006
Create Date: 2026-10-05
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261005_0007"
down_revision: str | None = "20260922_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mistake_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wrong_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "question_id", name="uq_mistake_user_question"),
    )
    op.create_index("ix_mistake_reviews_user_id", "mistake_reviews", ["user_id"])
    op.create_index("ix_mistake_reviews_question_id", "mistake_reviews", ["question_id"])
    op.create_index("ix_mistake_reviews_cleared_at", "mistake_reviews", ["cleared_at"])
    op.create_index("ix_mistake_reviews_created_at", "mistake_reviews", ["created_at"])
    op.create_index("ix_mistake_reviews_updated_at", "mistake_reviews", ["updated_at"])
    # The hot path: a student's open questions, oldest due first.
    op.create_index("idx_mistake_due", "mistake_reviews", ["user_id", "cleared_at", "due_at"])


def downgrade() -> None:
    op.drop_index("idx_mistake_due", table_name="mistake_reviews")
    op.drop_index("ix_mistake_reviews_updated_at", table_name="mistake_reviews")
    op.drop_index("ix_mistake_reviews_created_at", table_name="mistake_reviews")
    op.drop_index("ix_mistake_reviews_cleared_at", table_name="mistake_reviews")
    op.drop_index("ix_mistake_reviews_question_id", table_name="mistake_reviews")
    op.drop_index("ix_mistake_reviews_user_id", table_name="mistake_reviews")
    op.drop_table("mistake_reviews")
