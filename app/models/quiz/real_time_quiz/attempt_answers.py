from datetime import datetime
from sqlalchemy import ForeignKey, String, TIMESTAMP, Integer, Boolean, func
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import BaseModel


class AttemptAnswer(BaseModel):
    __tablename__ = "attempt_answers"


    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE")
    )

    question_id: Mapped[int] = mapped_column(Integer)

    selected_option: Mapped[str] = mapped_column(String(5))

    is_correct: Mapped[bool] = mapped_column(Boolean)

    answered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.now()
    )

    attempt = relationship("QuizAttempt", back_populates="answers")