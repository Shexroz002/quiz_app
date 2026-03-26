import enum
from datetime import datetime
from sqlalchemy import ForeignKey, String, Integer, DateTime, Enum as SqlEnum
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import BaseModel


class SessionType(str, enum.Enum):
    individual = "individual"
    group = "group"
    public = "public"


class SessionStatus(str, enum.Enum):
    waiting = "waiting"
    running = "running"
    finished = "finished"


class QuizSession(BaseModel):
    __tablename__ = "quiz_sessions"

    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE")
    )

    host_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    join_code: Mapped[str] = mapped_column(String(10), unique=True)

    status: Mapped[SessionStatus] = mapped_column(
        SqlEnum(SessionStatus, name="session_status"),
        nullable=False,
        default=SessionStatus.waiting,
        server_default="waiting",
    )
    session_type: Mapped[SessionType] = mapped_column(
        SqlEnum(SessionType, name="session_type"),
        nullable=False,
        default=SessionType.individual,
        server_default="individual",
    )
    max_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # waiting | running | finished

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    quiz = relationship("Quiz", back_populates="sessions")
    session_groups: Mapped[list["QuizSessionGroup"]] = relationship(
        "QuizSessionGroup",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    participants: Mapped[list["SessionParticipant"]] = relationship(
        "SessionParticipant",
        back_populates="session",
        cascade="all, delete",
    )

    attempts: Mapped[list["QuizAttempt"]] = relationship(
        "QuizAttempt",
        back_populates="session",
        cascade="all, delete",
    )