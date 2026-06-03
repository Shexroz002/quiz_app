import json

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.chat.chat_repo import ChatRepository
from app.repositories.chat.message_repo import MessageRepository
from app.schemas.chat.message_schema import MessageCreate, MessageUpdate
from app.websocket.chat.utils.event_type import EventType
from app.websocket.chat.utils.presence import now_iso


class RealTimeEventService:
    def __init__(self, mongo_db: AsyncIOMotorDatabase, db: AsyncSession, redis: Redis, pubsub):
        self.message_repo = MessageRepository(mongo_db)
        self.chat_repo = ChatRepository(db)
        self.redis = redis
        self.pubsub = pubsub

    async def message_new(self, message_dict: dict,sender_id) -> None:
        new_message = MessageCreate(**message_dict, sender_id=sender_id)
        message = await self.message_repo.create(new_message)
        chat_id = message.get("chat_id")
        chat_update = {
            "chat_id": chat_id,
            "message_text": message.get("text"),
            "sender_id": message.get("sender_id"),
            "created_at": message.get("created_at"),
        }
        await self.chat_repo.update_chat_last_message(**chat_update)
        new_message_payload = json.dumps({
            "type": EventType.MESSAGE_NEW,
            "chat_id": chat_id,
            "message": {
                "id": message.get("id"),
                "sender_id": message.get("sender_id"),
                "sender_name": "User " + str(message.get("sender_id", 1)),
                "content": message.get("text"),
                "message_id": message.get("_id"),
                "created_at": message.get("created_at").isoformat(),
            },
            "chat_preview": {
                "last_message_text": message.get("text"),
                "last_message_at": message.get("created_at").isoformat(),
                "unread_count": 68
            }
        })
        await self.redis.publish(f"chat:{chat_id}", new_message_payload)
        return None

    async def message_edit(self, message_dict: dict,sender_id) -> None:
        message_id = message_dict.get("message_id")
        new_text = message_dict.get("new_text")
        if not message_id or not new_text:
            return None

        new_text = str(new_text)
        message_id = str(message_id)
        message_edit = MessageUpdate(text=new_text)
        await self.message_repo.update(message_id, sender_id, message_edit)
        chat_id = message_dict.get("chat_id")
        edit_message_payload = json.dumps({
            "type": EventType.MESSAGE_EDITED,
            "chat_id": chat_id,
            "message": {
                "id": message_id,
                "sender_id": sender_id,
                "new_content": new_text,
                "edited_at": now_iso(),
                "affects_chat_preview": True
            }
        })
        await self.redis.publish(f"chat:{chat_id}", edit_message_payload)
        return None

    async def message_deleted(self, message_dict: dict,sender_id:int) -> None:
        message_id = message_dict.get("message_id")
        chat_id = message_dict.get("chat_id")
        if not message_id or not chat_id:
            return None

        message_id = str(message_id)
        chat_id = int(chat_id)
        await self.message_repo.soft_delete(message_id, sender_id)
        last_message= await self.message_repo.get_last_message(chat_id)
        delete_message_payload = json.dumps({
            "type": EventType.MESSAGE_DELETED,
            "chat_id": chat_id,
            "message": {
                "id": message_id,
                "sender_id": sender_id,
                "deleted_at": now_iso(),
                "affects_chat_preview": True
            },
            "chat_preview": {
                "last_message_text": last_message.get('text'),
                "last_message_at": last_message.get('created_at').isoformat() if last_message else None,
                "last_message_id": last_message.get("_id"),
                "unread_count": 68
            }
        })
        await self.redis.publish(f"chat:{chat_id}", delete_message_payload)
        return None

    async def message_reaction_add(self, message_dict: dict,sender_id:int) -> None:
        message_id = message_dict.get("message_id")
        emoji = message_dict.get("emoji")
        if not message_id or not emoji:
            return None
        message_id = str(message_id)
        emoji = str(emoji)
        reaction_data = await self.message_repo.toggle_reaction(message_id, sender_id, emoji)
        chat_id = message_dict.get("chat_id")
        reaction_add_payload = json.dumps({
            "type": EventType.MESSAGE_REACTION_ADD,
            "chat_id": chat_id,
            "message":reaction_data
        })
        await self.redis.publish(f"chat:{chat_id}", reaction_add_payload)
        return None

    async def message_mark_as_read(self, message_dict: dict,sender_id:int) -> None:
        chat_id = message_dict.get("chat_id")
        message_ids = message_dict.get("message_ids")
        if not chat_id or not message_ids:
            return None
        message_ids = [str(mid) for mid in message_ids]
        await self.message_repo.mark_as_read(message_ids)
        mark_as_read_payload = json.dumps({
            "type": EventType.MESSAGE_READ,
            "chat_id": chat_id,
            "message_ids": message_ids,
            "reader_id": sender_id,
            "read_at": now_iso()
        })
        await self.redis.publish(f"chat:{chat_id}", mark_as_read_payload)
        return None

    async def typing_update(self, message_dict: dict,sender_id:int) -> None:
        payload = json.dumps({"sender_id": sender_id, "is_typing": True, "type": EventType.TYPING_UPDATE})
        await self.redis.publish(f"chat:{message_dict['chat_id']}", payload)
