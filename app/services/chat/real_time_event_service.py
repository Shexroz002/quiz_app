import json

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat.chat_members import ChatMemberRole
from app.models.chat.chats import ChatType
from app.repositories.chat.chat_repo import ChatRepository
from app.repositories.chat.message_repo import MessageRepository
from app.schemas.chat.message_schema import MessageCreate, MessageUpdate
from app.services.chat.chat_service import _make_direct_key
from app.services.chat.exceptions import ChatAccessDeniedError, MessageNotFoundError
from app.websocket.chat.utils.event_type import EventType
from app.websocket.chat.utils.presence import now_iso


class RealTimeEventService:
    def __init__(self, mongo_db: AsyncIOMotorDatabase, db: AsyncSession, redis: Redis, pubsub,
                 origin_id: str | None = None):
        self.message_repo = MessageRepository(mongo_db)
        self.chat_repo = ChatRepository(db)
        self.redis = redis
        self.pubsub = pubsub
        self.db = db
        # Shu ulanishning belgisi. Publish qilingan har bir payloadga qo'shiladi,
        # shunda aynan shu ulanish o'z eventini qaytib olmaydi. Foydalanuvchining
        # boshqa qurilmalari boshqa origin'ga ega, ular eventni oladi.
        self.origin_id = origin_id

    def _ack(self, chat_id: int, message: dict, message_dict: dict) -> dict:
        """Yuboruvchiga qaytariladigan tasdiq: server bergan message_id shu yerda."""
        created_at = message.get("created_at")
        return {
            "type": EventType.MESSAGE_ACK,
            "chat_id": chat_id,
            "message_id": str(message.get("_id")),
            "created_at": created_at.isoformat() if created_at else None,
            "client_message_id": message_dict.get("client_message_id"),
        }

    async def _ensure_member(self, chat_id: int, user_id: int) -> int:
        """Foydalanuvchi chat a'zosi ekanini tekshiradi va tekshirilgan chat_id ni qaytaradi."""
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            raise ChatAccessDeniedError("chat_id noto'g'ri")
        if not await self.chat_repo.is_member(chat_id, user_id):
            raise ChatAccessDeniedError("Siz bu chat a'zosi emassiz")
        return chat_id

    async def _load_accessible_message(self, message_id: str, user_id: int) -> tuple[dict, int]:
        """Xabarni yuklaydi, a'zolikni tekshiradi va xabarning haqiqiy chat_id sini qaytaradi.

        chat_id client payload'idan emas, xabar hujjatidan olinadi - aks holda
        foydalanuvchi bir chatdagi xabar haqidagi eventni boshqa chatga publish qila oladi.
        """
        doc = await self.message_repo.get_by_id(str(message_id))
        if not doc:
            raise MessageNotFoundError()
        chat_id = await self._ensure_member(doc["chat_id"], user_id)
        return doc, chat_id

    async def message_new(self, message_dict: dict, sender_id) -> dict | None:
        chat_id = await self._ensure_member(message_dict.get("chat_id"), sender_id)
        new_message = MessageCreate(**{**message_dict, "chat_id": chat_id}, sender_id=sender_id)
        message = await self.message_repo.create(new_message)
        chat_update = {
            "chat_id": chat_id,
            "message_text": message.get("text"),
            "sender_id": message.get("sender_id"),
            "created_at": message.get("created_at"),
        }
        await self.chat_repo.update_chat_last_message(**chat_update)
        new_message_payload = json.dumps({
            "type": EventType.MESSAGE_NEW,
            "origin": self.origin_id,
            "chat_id": chat_id,
            "message": {
                "id": message.get("id"),
                "sender_id": message.get("sender_id"),
                "sender_name": "User " + str(message.get("sender_id", 1)),
                "reply_to_message_id": message.get("reply_to_message_id"),
                "attachments": message.get("attachments", []),
                "mentions": message.get("mentions", []),
                "content": message.get("text"),
                "message_id": message.get("_id"),
                "created_at": message.get("created_at").isoformat(),
            },
            "chat_preview": {
                "chat_id": chat_id,
                "last_message_text": message.get("text"),
                "last_message_at": message.get("created_at").isoformat()
            }
        })
        await self.redis.publish(f"chat:{chat_id}", new_message_payload)
        return self._ack(chat_id, message, message_dict)

    async def forward_message(self, message_dict: dict, sender_id: int) -> dict | None:
        original_message_id = message_dict.get("original_message_id")
        target_chat_id = message_dict.get("chat_id")
        sender_name = message_dict.get("sender_name")
        if not original_message_id or not target_chat_id:
            return None

        # Manba chatga ham, maqsad chatga ham a'zolik shart: aks holda ko'rishga
        # ruxsati yo'q xabarni o'ziga forward qilib o'qib olish mumkin bo'ladi.
        await self._load_accessible_message(original_message_id, sender_id)
        target_chat_id = await self._ensure_member(target_chat_id, sender_id)

        forwarded_message = await self.message_repo.forward_message(
            original_message_id=str(original_message_id),
            target_chat_id=target_chat_id,
            current_user_id=sender_id,
            sender_name=str(sender_name)
        )
        if not forwarded_message:
            return None
        chat_update = {
            "chat_id": target_chat_id,
            "message_text": forwarded_message.get("text"),
            "sender_id": forwarded_message.get("sender_id"),
            "created_at": forwarded_message.get("created_at"),
        }
        await self.chat_repo.update_chat_last_message(**chat_update)
        forward_message_payload = json.dumps({
            "type": EventType.MESSAGE_FORWARD,
            "origin": self.origin_id,
            "chat_id": target_chat_id,
            "message": {
                "id": forwarded_message.get("id"),
                "sender_id": forwarded_message.get("sender_id"),
                "sender_name": forwarded_message.get("sender_name"),
                "content": forwarded_message.get("text"),
                "message_id": str(forwarded_message.get("_id")),
                "created_at": forwarded_message.get("created_at").isoformat(),
                "forwarded_from": forwarded_message.get("forwarded_from"),
            },
            "chat_preview": {
                "chat_id": target_chat_id,
                "last_message_text": forwarded_message.get("text"),
                "last_message_at": forwarded_message.get("created_at").isoformat(),
            }
        },default=str)
        await self.redis.publish(f"chat:{target_chat_id}", forward_message_payload)
        return self._ack(target_chat_id, forwarded_message, message_dict)

    async def message_edit(self, message_dict: dict, sender_id) -> None:
        message_id = message_dict.get("message_id")
        new_text = message_dict.get("new_text")
        if not message_id or not new_text:
            return None

        new_text = str(new_text)
        message_id = str(message_id)
        _, chat_id = await self._load_accessible_message(message_id, sender_id)

        message_edit = MessageUpdate(text=new_text)
        message = await self.message_repo.update(message_id, sender_id, message_edit)
        if not message:
            raise ChatAccessDeniedError("Faqat o'z xabaringizni tahrirlay olasiz")

        edit_message_payload = json.dumps({
            "type": EventType.MESSAGE_EDITED,
            "origin": self.origin_id,
            "chat_id": chat_id,
            "message": {
                "id": message_id,
                "sender_id": sender_id,
                "new_content": message.get("text"),
                "edited_at": now_iso(),
                "mentions": message.get("mentions", []),
                "affects_chat_preview": True,
                "reply_to_message_id": message.get("reply_to_message_id"),
            }
        })
        await self.redis.publish(f"chat:{chat_id}", edit_message_payload)
        return None

    async def message_deleted(self, message_dict: dict, sender_id: int) -> None:
        message_id = message_dict.get("message_id")
        if not message_id:
            return None

        message_id = str(message_id)
        _, chat_id = await self._load_accessible_message(message_id, sender_id)

        deleted = await self.message_repo.soft_delete(message_id, sender_id)
        if not deleted:
            raise ChatAccessDeniedError("Faqat o'z xabaringizni o'chira olasiz")

        last_message = await self.message_repo.get_last_message(chat_id)
        delete_message_payload = json.dumps({
            "type": EventType.MESSAGE_DELETED,
            "origin": self.origin_id,
            "chat_id": chat_id,
            "message": {
                "id": message_id,
                "sender_id": sender_id,
                "deleted_at": now_iso(),
                "affects_chat_preview": True
            },
            "chat_preview": {
                "last_message_text": last_message.get("text") if last_message else None,
                "last_message_at": last_message.get("created_at").isoformat() if last_message else None,
                "last_message_id": last_message.get("_id") if last_message else None,
            }
        })
        await self.redis.publish(f"chat:{chat_id}", delete_message_payload)
        return None

    async def message_reaction_add(self, message_dict: dict, sender_id: int) -> None:
        message_id = message_dict.get("message_id")
        emoji = message_dict.get("emoji")
        if not message_id or not emoji:
            return None
        message_id = str(message_id)
        emoji = str(emoji)
        _, chat_id = await self._load_accessible_message(message_id, sender_id)

        reaction_data = await self.message_repo.toggle_reaction(message_id, sender_id, emoji)
        reaction_add_payload = json.dumps({
            "type": EventType.MESSAGE_REACTION_ADD,
            "origin": self.origin_id,
            "chat_id": chat_id,
            "message": reaction_data
        })
        await self.redis.publish(f"chat:{chat_id}", reaction_add_payload)
        return None

    async def message_mark_as_read(self, message_dict: dict, sender_id: int) -> None:
        message_id = message_dict.get("message_id")
        if not message_id:
            return None
        message_id = str(message_id)
        _, chat_id = await self._load_accessible_message(message_id, sender_id)

        mark_as_read_payload = json.dumps({
            "type": EventType.MESSAGE_READ,
            "origin": self.origin_id,
            "chat_id": chat_id,
            "message_ids": message_id,
            "reader_id": sender_id,
            "read_at": now_iso()
        })
        await self.redis.publish(f"chat:{chat_id}", mark_as_read_payload)
        await self.chat_repo.update_chat_member_last_message_read_id(chat_id, sender_id, message_id, )
        return None

    async def new_chat(self, message_dict: dict, sender_id: int) -> dict | None:
        target_user_id = message_dict.pop("target_user_id")
        text = message_dict.get("text")
        if not target_user_id or not text:
            return None
        try:
            target_user_id = int(target_user_id)
        except (TypeError, ValueError):
            raise ChatAccessDeniedError("target_user_id noto'g'ri")
        if target_user_id == sender_id:
            raise ChatAccessDeniedError("O'zingiz bilan chat ocholmaysiz")
        key = _make_direct_key(sender_id, target_user_id)

        existing = await self.chat_repo.get_by_direct_key(key)
        if existing:
            chat_id = existing.id
        else:
            chat = await self.chat_repo.create_chat(
                name="",
                chat_type=ChatType.PRIVATE,
                owner_id=sender_id,
                direct_key=key,
            )

            await self.chat_repo.add_member(chat.id, sender_id, ChatMemberRole.MEMBER)
            await self.chat_repo.add_member(chat.id, target_user_id, ChatMemberRole.MEMBER)

            await self.db.commit()
            await self.db.refresh(chat)
            chat_id = chat.id
        message_dict['chat_id'] = chat_id
        await self.pubsub.subscribe(f"chat:{chat_id}")
        # Yangi chatning chat_id sini client faqat shu ack orqali biladi.
        return await self.message_new(message_dict, sender_id)

    async def typing_update(self, message_dict: dict, sender_id: int) -> None:
        chat_id = await self._ensure_member(message_dict.get("chat_id"), sender_id)
        payload = json.dumps({"sender_id": sender_id, "is_typing": True,
                              "type": EventType.TYPING_UPDATE, "origin": self.origin_id})
        await self.redis.publish(f"chat:{chat_id}", payload)
