from typing import Any, Mapping

from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException, status

from app.core.database.mongodb import MongoDep
from app.repositories.chat.message_repo import MessageRepository
from app.schemas.chat.message_schema import MessageCreate, MessageUpdate


class MessageService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.repo = MessageRepository(db)

    async def send_message(self, data: MessageCreate, chat_id: int, sender_id: int) -> dict:
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
            limit: int = 50,
            before_id: str = None,
    ) -> list[Mapping[str, Any]]:
        return await self.repo.get_chat_messages(chat_id, limit, before_id)

    async def edit_message(
            self,
            message_id: str,
            sender_id: int,
            data: MessageUpdate,
    ) -> Mapping[str, Any]:
        doc = await self.repo.update(message_id, sender_id, data)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Xabar topilmadi yoki ruxsat yo'q",
            )
        return doc

    async def delete_message(self, message_id: str, sender_id: int) -> dict:
        deleted = await self.repo.soft_delete(message_id, sender_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Xabar topilmadi yoki ruxsat yo'q",
            )
        return {"status": "deleted", "message_id": message_id}

    async def toggle_reaction(self, message_id: str, user_id: int, emoji: str) -> Mapping[str, Any]:
        doc = await self.repo.toggle_reaction(message_id, user_id, emoji)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Xabar topilmadi",
            )
        return doc

    async def message_mark_as_read(self, message_ids: list[str]) -> None:
        await self.repo.mark_as_read(message_ids)

    async def view_message(self, message_id: str) -> None:
        await self.repo.increment_views(message_id)


def get_message_service(db: MongoDep) -> MessageService:
    return MessageService(db)
