import enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ExplanationStatus(str, enum.Enum):
    """Where a bank question's solution is in its life."""

    pending = "pending"
    ready = "ready"
    #: The model solved it on its own and reached a different option than the
    #: key. Either the solution or the key is wrong; neither is shown.
    rejected = "rejected"
    #: The model could not be reached. Retried on the next request.
    failed = "failed"


class SolveStatus(str, enum.Enum):
    """A student's own problem, from photo to solution."""

    #: The photo has been read; waiting for the student to confirm the text.
    recognized = "recognized"
    pending = "pending"
    done = "done"
    failed = "failed"


class FeedbackVerdict(str, enum.Enum):
    helpful = "helpful"
    unclear = "unclear"
    wrong = "wrong"


class QuestionExplanation(BaseModel):
    """A step-by-step solution for one bank question.

    Content, not chat: written once, checked against the key, then served to
    every student who asks. The questions themselves are untouched — this table
    only points at them.
    """

    __tablename__ = "question_explanations"

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[ExplanationStatus] = mapped_column(
        Enum(ExplanationStatus, name="explanation_status"),
        nullable=False,
        default=ExplanationStatus.pending,
    )
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    #: The model solved the question without being told the answer and landed on
    #: the keyed option. False on every row that is not ``ready``.
    matches_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    unclear_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class SolveRequest(BaseModel):
    """One problem a student brought in, by photo or by typing it."""

    __tablename__ = "solve_requests"
    __table_args__ = (
        # The daily limit counts a student's rows since midnight.
        Index("idx_solve_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[SolveStatus] = mapped_column(
        Enum(SolveStatus, name="solve_status"), nullable=False, default=SolveStatus.pending
    )
    input_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ExplanationFeedback(BaseModel):
    """"Was it clear?" — the only measure of a solution's quality we have."""

    __tablename__ = "explanation_feedback"
    __table_args__ = (
        CheckConstraint(
            "(explanation_id IS NULL) <> (solve_request_id IS NULL)",
            name="ck_feedback_one_target",
        ),
        UniqueConstraint("user_id", "explanation_id", name="uq_feedback_user_explanation"),
        UniqueConstraint("user_id", "solve_request_id", name="uq_feedback_user_request"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    explanation_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_explanations.id", ondelete="CASCADE"), nullable=True
    )
    solve_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("solve_requests.id", ondelete="CASCADE"), nullable=True
    )
    verdict: Mapped[FeedbackVerdict] = mapped_column(
        Enum(FeedbackVerdict, name="feedback_verdict"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
