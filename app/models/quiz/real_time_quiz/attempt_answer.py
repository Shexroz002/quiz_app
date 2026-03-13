from datetime import datetime
from sqlalchemy import UniqueConstraint, ForeignKey, Integer, String, Boolean, TIMESTAMP, func, Index
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import BaseModel


class AttemptAnswer(BaseModel):
    __tablename__ = "attempt_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),
        Index("idx_attempt_question", "attempt_id", "question_id"),
    )

    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE")
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE")
    )

    selected_option: Mapped[str] = mapped_column(String(5))

    is_correct: Mapped[bool] = mapped_column(Boolean)

    answered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.now()
    )

    attempt = relationship("QuizAttempt", back_populates="answers")
    question = relationship("Question", back_populates="attempt_answers")
