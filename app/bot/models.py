from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class TelegramQuizRoom(BaseModel):
    __tablename__ = "telegram_quiz_rooms"
    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_telegram_room_message"),)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"), unique=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    bot_username: Mapped[str] = mapped_column(String(64))
    published_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    leaderboard_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TelegramChannel(BaseModel):
    """A channel or group an admin has already proved they can publish to.

    Only a convenience: the rights are re-checked on every publish, so a stale
    row can never let anyone post. It exists so the chat is chosen from a list
    instead of being hunted for before every quiz.
    """

    __tablename__ = "telegram_channels"
    __table_args__ = (UniqueConstraint("user_id", "chat_id", name="uq_telegram_channel_owner"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(255))
    #: "channel" or "group" -- which list the row belongs to.
    kind: Mapped[str] = mapped_column(String(16), server_default="channel")


class TelegramSinglePlayerResultDelivery(BaseModel):
    __tablename__ = "telegram_single_player_result_deliveries"

    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), unique=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class TelegramRoomAnalysisDelivery(BaseModel):
    """Private-chat outbox for one room participant's personal analysis message."""

    __tablename__ = "telegram_room_analysis_deliveries"

    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), unique=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
