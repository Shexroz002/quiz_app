from typing import Any, Mapping

from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.core.database.mongodb import MongoDep
from app.repositories.chat.chat_repo import ChatRepository
from app.repositories.chat.message_repo import MessageRepository
from app.schemas.chat.message_schema import MessageCreate, MessageUpdate


class MessageService:
    def __init__(self, db: AsyncIOMotorDatabase, chat_repo: ChatRepository):
        self.repo = MessageRepository(db)
        self.chat_repo = chat_repo

    async def _ensure_member(self, chat_id: int, user_id: int) -> None:
        if not await self.chat_repo.is_member(chat_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Siz bu chat a'zosi emassiz",
            )

    async def _ensure_message_access(self, message_id: str, user_id: int) -> Mapping[str, Any]:
        """Xabarni yuklaydi va foydalanuvchi uning chatiga a'zoligini tekshiradi."""
        doc = await self.repo.get_by_id(message_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Xabar topilmadi",
            )
        await self._ensure_member(doc["chat_id"], user_id)
        return doc

    async def send_message(self, data: MessageCreate, chat_id: int, sender_id: int) -> dict:
        await self._ensure_member(chat_id, sender_id)
        if not data.text and not data.attachments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text yoki attachment bo'lishi shart",
            )
        data = data.model_copy(update={"chat_id": chat_id, "sender_id": sender_id})
        return await self.repo.create(data)

    async def get_history(
            self,
            chat_id: int,
            current_user_id: int,
            limit: int = 50,
            before_id: str = None,
    ) -> list[Mapping[str, Any]]:
        await self._ensure_member(chat_id, current_user_id)
        return await self.repo.get_chat_messages(chat_id, limit, before_id)

    async def edit_message(
            self,
            message_id: str,
            sender_id: int,
            data: MessageUpdate,
    ) -> Mapping[str, Any]:
        await self._ensure_message_access(message_id, sender_id)
        doc = await self.repo.update(message_id, sender_id, data)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Faqat o'z xabaringizni tahrirlay olasiz",
            )
        return doc

    async def delete_message(self, message_id: str, sender_id: int) -> dict:
        await self._ensure_message_access(message_id, sender_id)
        deleted = await self.repo.soft_delete(message_id, sender_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Faqat o'z xabaringizni o'chira olasiz",
            )
        return {"status": "deleted", "message_id": message_id}

    async def toggle_reaction(self, message_id: str, user_id: int, emoji: str) -> Mapping[str, Any]:
        await self._ensure_message_access(message_id, user_id)
        doc = await self.repo.toggle_reaction(message_id, user_id, emoji)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Xabar topilmadi",
            )
        return doc

    async def message_mark_as_read(self, message_ids: list[str], current_user_id: int) -> None:
        if not message_ids:
            return None
        chat_ids = await self.repo.get_chat_ids_for_messages(message_ids)
        allowed = await self.chat_repo.get_member_chat_ids(list(chat_ids), current_user_id)
        if chat_ids - allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Siz bu chat a'zosi emassiz",
            )
        await self.repo.mark_as_read(message_ids)

    async def view_message(self, message_id: str, current_user_id: int) -> None:
        await self._ensure_message_access(message_id, current_user_id)
        await self.repo.increment_views(message_id)


def get_message_service(
        db: MongoDep,
        sql_db: AsyncSession = Depends(get_db),
) -> MessageService:
    return MessageService(db, ChatRepository(sql_db))
