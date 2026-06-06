from datetime import datetime
import enum
from sqlalchemy import (
    String,
    Enum as SqlEnum,
    ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


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
        nullable=False,
        default=datetime.utcnow,
    )

    last_read_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("chat_user_idx", "chat_id", "user_id", unique=True),
    )