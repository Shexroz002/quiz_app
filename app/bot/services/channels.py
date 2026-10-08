"""Chats an admin has already bound to the bot: channels and groups.

Purely a convenience list: publishing re-checks the rights every time
(``ensure_publish_rights``), so a row here is a shortcut, never a permission.
"""

from sqlalchemy import delete, select

from app.bot.models import TelegramChannel
from app.core.database.base import AsyncSessionLocal

CHANNEL = "channel"
GROUP = "group"


async def remember_chat(user_id: int, chat_id: int, title: str, kind: str = CHANNEL) -> None:
    """Keep the chat for next time, refreshing a title that has changed."""
    async with AsyncSessionLocal() as db:
        chat = (await db.execute(
            select(TelegramChannel).where(
                TelegramChannel.user_id == user_id,
                TelegramChannel.chat_id == chat_id,
            )
        )).scalar_one_or_none()
        if chat is None:
            db.add(TelegramChannel(
                user_id=user_id, chat_id=chat_id, title=title, kind=kind,
            ))
        else:
            chat.title = title
            chat.kind = kind
        await db.commit()


async def remembered_chats(user_id: int, kind: str = CHANNEL) -> list[dict]:
    """The user's chats of one kind, most recently used first."""
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(TelegramChannel.chat_id, TelegramChannel.title)
            .where(
                TelegramChannel.user_id == user_id,
                TelegramChannel.kind == kind,
            )
            .order_by(TelegramChannel.updated_at.desc())
        )).all()
    return [{"chat_id": chat_id, "title": title} for chat_id, title in rows]


async def forget_chat(user_id: int, chat_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(TelegramChannel).where(
                TelegramChannel.user_id == user_id,
                TelegramChannel.chat_id == chat_id,
            )
        )
        await db.commit()
