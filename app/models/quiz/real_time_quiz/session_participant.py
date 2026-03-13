from datetime import datetime
from sqlalchemy import ForeignKey, String, TIMESTAMP, func, Boolean, Enum as SQLEnum
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import BaseModel
from enum import Enum


class ParticipantStatus(str, Enum):
    PREPARING = "preparing"
    READY = "ready"
    DISCONNECTED = "disconnected"


class SessionParticipant(BaseModel):
    __tablename__ = "session_participants"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE")
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    participant_status: Mapped[ParticipantStatus] = mapped_column(
        SQLEnum(ParticipantStatus, name="participant_status_enum"),
        default=ParticipantStatus.PREPARING,
        nullable=False
    )

    nickname: Mapped[str] = mapped_column(String(50))

    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.now()
    )

    is_host: Mapped[bool] = mapped_column(Boolean, default=False)

    session = relationship("QuizSession", back_populates="participants")
    user = relationship("User", back_populates="quiz_participation")
