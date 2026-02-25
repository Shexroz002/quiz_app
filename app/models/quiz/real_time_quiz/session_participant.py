from datetime import datetime
from sqlalchemy import ForeignKey, String, TIMESTAMP, func, Boolean
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import BaseModel


class SessionParticipant(BaseModel):
    __tablename__ = "session_participants"


    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE")
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    nickname: Mapped[str] = mapped_column(String(50))

    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.now()
    )

    is_host: Mapped[bool] = mapped_column(Boolean, default=False)

    session = relationship("QuizSession", back_populates="participants")
    user = relationship("User", back_populates="quiz_participation")