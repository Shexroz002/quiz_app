from sqlalchemy import ForeignKey, Boolean, Integer
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

    current_question: Mapped[int] = mapped_column(Integer, default=1)

    finished: Mapped[bool] = mapped_column(Boolean, default=False)

    answers = relationship(
        "AttemptAnswer",
        back_populates="attempt",
        cascade="all, delete"
    )
    session = relationship("QuizSession", back_populates="attempts")