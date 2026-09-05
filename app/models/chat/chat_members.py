from datetime import datetime
import enum
from sqlalchemy import (
    String,
    Enum as SqlEnum,
    ForeignKey, Index, DateTime
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.utils.datetime import utc_now


class ChatMemberRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"

class ChatMember(BaseModel):
    __tablename__ = "chat_members"
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ChatMemberRole] = mapped_column(
        SqlEnum(ChatMemberRole, name="chat_member_role"),
        nullable=False,
        default=ChatMemberRole.MEMBER,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    last_read_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("chat_user_idx", "chat_id", "user_id", unique=True),
    )
    chat = relationship(
        "Chat",
        back_populates="members"
    )
