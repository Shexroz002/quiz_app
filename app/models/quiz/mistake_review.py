from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class MistakeReview(BaseModel):
    """One question a student got wrong, and when it comes back.

    The questions themselves are not stored here: every wrong answer already
    lives in ``attempt_answers``. This table only holds the *review state* — the
    schedule, the streak and whether the question has been cleared — so the bank
    can be rebuilt from answers at any time without losing a student's progress.

    Intervals are deliberately simple so the app can explain them: a wrong
    answer brings the question back in one day, the first correct answer pushes
    it to three, the second to seven and clears it. Two correct answers in a row
    is the only way out; there is no manual removal (owner decision).
    """

    __tablename__ = "mistake_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_mistake_user_question"),
        # The due query is "my open questions, due by now", in that order.
        Index("idx_mistake_due", "user_id", "cleared_at", "due_at"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: When the question returns to the bank. Due when this is in the past.
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Correct answers in a row, 0..2. Reaching 2 clears the question.
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    #: How many times the student has got this question wrong, ever. Shown to
    #: the student as "you have missed this twice".
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: Set when the question leaves the bank. Kept rather than deleted so the
    #: student can be shown how many questions they have closed.
    cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    question = relationship("Question", lazy="joined")
