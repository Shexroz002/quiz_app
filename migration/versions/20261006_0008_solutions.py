"""Step-by-step solutions: bank explanations, students' own problems, feedback.

Three new tables and nothing else. No existing table gains or loses a column,
so quiz generation, sessions, the teacher panel and the Telegram bot are not
affected.

- question_explanations: one checked solution per bank question, written once
  and served to everyone.
- solve_requests: a student's own problem, from photo to solution; also what
  the daily limit counts.
- explanation_feedback: "was it clear?" per student, on either of the above.

Revision ID: 20261006_0008
Revises: 20261005_0007
Create Date: 2026-10-06
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20261006_0008"
down_revision: str | None = "20261005_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXPLANATION_STATUS = ("pending", "ready", "rejected", "failed")
SOLVE_STATUS = ("recognized", "pending", "done", "failed")
FEEDBACK_VERDICT = ("helpful", "unclear", "wrong")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    explanation_status = postgresql.ENUM(*EXPLANATION_STATUS, name="explanation_status", create_type=False)
    solve_status = postgresql.ENUM(*SOLVE_STATUS, name="solve_status", create_type=False)
    feedback_verdict = postgresql.ENUM(*FEEDBACK_VERDICT, name="feedback_verdict", create_type=False)
    bind = op.get_bind()
    explanation_status.create(bind, checkfirst=True)
    solve_status.create(bind, checkfirst=True)
    feedback_verdict.create(bind, checkfirst=True)

    op.create_table(
        "question_explanations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("status", explanation_status, nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("matches_key", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("helpful_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unclear_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", name="uq_question_explanations_question_id"),
    )
    op.create_index("ix_question_explanations_created_at", "question_explanations", ["created_at"])
    op.create_index("ix_question_explanations_updated_at", "question_explanations", ["updated_at"])

    op.create_table(
        "solve_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(30), nullable=False),
        sa.Column("status", solve_status, nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("input_image_path", sa.String(500), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_solve_requests_user_id", "solve_requests", ["user_id"])
    op.create_index("ix_solve_requests_created_at", "solve_requests", ["created_at"])
    op.create_index("ix_solve_requests_updated_at", "solve_requests", ["updated_at"])
    # The daily limit: a student's rows since midnight.
    op.create_index("idx_solve_user_created", "solve_requests", ["user_id", "created_at"])

    op.create_table(
        "explanation_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("explanation_id", sa.Integer(), nullable=True),
        sa.Column("solve_request_id", sa.Integer(), nullable=True),
        sa.Column("verdict", feedback_verdict, nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["explanation_id"], ["question_explanations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["solve_request_id"], ["solve_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(explanation_id IS NULL) <> (solve_request_id IS NULL)",
            name="ck_feedback_one_target",
        ),
        sa.UniqueConstraint("user_id", "explanation_id", name="uq_feedback_user_explanation"),
        sa.UniqueConstraint("user_id", "solve_request_id", name="uq_feedback_user_request"),
    )
    op.create_index("ix_explanation_feedback_user_id", "explanation_feedback", ["user_id"])
    op.create_index("ix_explanation_feedback_created_at", "explanation_feedback", ["created_at"])
    op.create_index("ix_explanation_feedback_updated_at", "explanation_feedback", ["updated_at"])


def downgrade() -> None:
    op.drop_table("explanation_feedback")
    op.drop_index("idx_solve_user_created", table_name="solve_requests")
    op.drop_table("solve_requests")
    op.drop_table("question_explanations")
    bind = op.get_bind()
    for name in ("feedback_verdict", "solve_status", "explanation_status"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
