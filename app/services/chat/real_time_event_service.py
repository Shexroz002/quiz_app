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
from app.websocket.chat.utils.event_type import EventType
from app.websocket.chat.utils.presence import now_iso


class RealTimeEventService:
    def __init__(self, mongo_db: AsyncIOMotorDatabase, db: AsyncSession, redis: Redis, pubsub):
        self.message_repo = MessageRepository(mongo_db)
        self.chat_repo = ChatRepository(db)
        self.redis = redis
        self.pubsub = pubsub
        self.db = db

    async def message_new(self, message_dict: dict, sender_id) -> None:
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
        return None

    async def forward_message(self, message_dict: dict, sender_id: int) -> None:
        original_message_id = message_dict.get("original_message_id")
        target_chat_id = message_dict.get("chat_id")
        sender_name = message_dict.get("sender_name")
        if not original_message_id or not target_chat_id:
            return None
        forwarded_message = await self.message_repo.forward_message(
            original_message_id=str(original_message_id),
            target_chat_id=int(target_chat_id),
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
        return None

    async def message_edit(self, message_dict: dict, sender_id) -> None:
        message_id = message_dict.get("message_id")
        new_text = message_dict.get("new_text")
        if not message_id or not new_text:
            return None

        new_text = str(new_text)
        message_id = str(message_id)
        message_edit = MessageUpdate(text=new_text)
        message = await self.message_repo.update(message_id, sender_id, message_edit)
        chat_id = message_dict.get("chat_id")
        edit_message_payload = json.dumps({
            "type": EventType.MESSAGE_EDITED,
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
        chat_id = message_dict.get("chat_id")
        if not message_id or not chat_id:
            return None

        message_id = str(message_id)
        chat_id = int(chat_id)
        await self.message_repo.soft_delete(message_id, sender_id)
        last_message = await self.message_repo.get_last_message(chat_id)
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
                "last_message_id": last_message.get("_id")
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
        reaction_data = await self.message_repo.toggle_reaction(message_id, sender_id, emoji)
        chat_id = message_dict.get("chat_id")
        reaction_add_payload = json.dumps({
            "type": EventType.MESSAGE_REACTION_ADD,
            "chat_id": chat_id,
            "message": reaction_data
        })
        await self.redis.publish(f"chat:{chat_id}", reaction_add_payload)
        return None

    async def message_mark_as_read(self, message_dict: dict, sender_id: int) -> None:
        chat_id = message_dict.get("chat_id")
        message_id = message_dict.get("message_id")
        if not chat_id or not message_id:
            return None
        message_id = str(message_id)
        chat_id = int(chat_id)
        mark_as_read_payload = json.dumps({
            "type": EventType.MESSAGE_READ,
            "chat_id": chat_id,
            "message_ids": message_id,
            "reader_id": sender_id,
            "read_at": now_iso()
        })
        await self.redis.publish(f"chat:{chat_id}", mark_as_read_payload)
        await self.chat_repo.update_chat_member_last_message_read_id(chat_id, sender_id, message_id, )
        return None

    async def new_chat(self, message_dict: dict, sender_id: int) -> None:
        target_user_id = message_dict.pop("target_user_id")
        text = message_dict.get("text")
        if not target_user_id or not text:
            return None
        target_user_id = int(target_user_id)
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
        await self.message_new(message_dict, sender_id)
        return None

    async def typing_update(self, message_dict: dict, sender_id: int) -> None:
        payload = json.dumps({"sender_id": sender_id, "is_typing": True, "type": EventType.TYPING_UPDATE})
        await self.redis.publish(f"chat:{message_dict['chat_id']}", payload)
