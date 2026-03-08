from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    String,
    Text,
    ForeignKey,
    DateTime,
    Boolean,
    Enum,
    JSON,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class NotificationType(str, PyEnum):
    FRIEND_REQUEST = "friend_request"
    FRIEND_ACCEPTED = "friend_accepted"
    TEST_INVITE = "test_invite"
    TEST_REMINDER = "test_reminder"
    TEST_RESULT = "test_result"
    ACHIEVEMENT = "achievement"
    TEACHER_MESSAGE = "teacher_message"
    COMPETITION_RESULT = "competition_result"
    SYSTEM = "system"


class NotificationActionType(str, PyEnum):
    NONE = "none"
    FRIEND_REQUEST = "friend_request"   # accept / reject
    TEST_INVITE = "test_invite"         # accept / reject
    OPEN_TEST = "open_test"
    OPEN_CHAT = "open_chat"
    OPEN_RESULT = "open_result"


class Notification(BaseModel):
    __tablename__ = "notifications"

    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    sender_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType),
        nullable=False,
        index=True,
    )

    action_type: Mapped[NotificationActionType] = mapped_column(
        Enum(NotificationActionType),
        default=NotificationActionType.NONE,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    recipient = relationship("User", foreign_keys=[recipient_id])
    sender = relationship("User", foreign_keys=[sender_id])