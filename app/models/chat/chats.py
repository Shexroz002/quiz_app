import enum
from datetime import datetime

from sqlalchemy import (
    String,
    Enum as SqlEnum,
    ForeignKey, DateTime
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ChatType(str, enum.Enum):
    PRIVATE = "PRIVATE"
    GROUP = "GROUP"
    CHANNEL = "CHANNEL"


class Chat(BaseModel):
    __tablename__ = "chats"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    chat_type: Mapped[ChatType] = mapped_column(
        SqlEnum(ChatType, name="chat_type"),
        nullable=False,
        default=ChatType.PRIVATE,
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_message_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_sender_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    last_message_created_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )

    direct_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    members = relationship(
        "ChatMember",
        back_populates="chat",
        cascade="all, delete-orphan"
    )