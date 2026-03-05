from datetime import datetime

from sqlalchemy import ForeignKey, Boolean, Integer, DateTime, func
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import BaseModel


class QuizAttempt(BaseModel):
    __tablename__ = "quiz_attempts"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE")
    )

    participant_id: Mapped[int] = mapped_column(
        ForeignKey("session_participants.id", ondelete="CASCADE")
    )

    score: Mapped[int] = mapped_column(Integer, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    wrong_answers: Mapped[int] = mapped_column(Integer, default=0, nullable=True)

    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=True
    )  # Set when the participant finishes the quiz

    answers = relationship(
        "AttemptAnswer",
        back_populates="attempt",
        cascade="all, delete"
    )
    session = relationship("QuizSession", back_populates="attempts")
