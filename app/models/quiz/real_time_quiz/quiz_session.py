from datetime import datetime
from sqlalchemy import ForeignKey, String, TIMESTAMP, Integer, DateTime
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import BaseModel


class QuizSession(BaseModel):
    __tablename__ = "quiz_sessions"

    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE")
    )

    host_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    join_code: Mapped[str] = mapped_column(String(10), unique=True)

    status: Mapped[str] = mapped_column(
        String,
        default="waiting"
    )
    # waiting | running | finished

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    quiz = relationship("Quiz", back_populates="sessions")

    participants = relationship(
        "SessionParticipant",
        back_populates="session",
        cascade="all, delete"
    )
    attempts = relationship(
        "QuizAttempt",
        back_populates="session",
        cascade="all, delete"
    )