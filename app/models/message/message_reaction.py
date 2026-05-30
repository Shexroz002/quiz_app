from sqlalchemy import (
    String,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class MessageReaction(BaseModel):
    __tablename__ = "message_reaction"
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reaction: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", "reaction", name="uq_message_user_reaction"
        ),
        Index("uq_message_user_reaction_idx", "message_id", "user_id", unique=True),
    )
