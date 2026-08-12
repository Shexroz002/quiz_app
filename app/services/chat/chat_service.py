from fastapi import HTTPException, status, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.core.database.mongodb import MongoDep
from app.core.database.redis import redis_client
from app.models.chat.chat_members import ChatMemberRole
from app.models.chat.chats import ChatType
from app.repositories.chat.chat_repo import ChatRepository
from app.repositories.chat.message_repo import MessageRepository
from app.schemas.chat.chat_list import LastMessageOut, ChatListItemOut, ChatListOut
from app.schemas.chat.chat_schema import CreateGroupChatSchema, CreatePrivateChatSchema


def _make_direct_key(user1_id: int, user2_id: int) -> str:
    a, b = sorted([user1_id, user2_id])
    return f"{a}:{b}"


class ChatService:
    def __init__(self, db: AsyncSession, mongo: AsyncIOMotorDatabase, redis):
        self.db = db
        self.repo = ChatRepository(db)
        self.message_repo = MessageRepository(mongo)
        self.redis = redis

    async def create_group_chat(
            self,
            owner_id: int,
            data: CreateGroupChatSchema,
    ):
        chat = await self.repo.create_chat(
            name=data.name,
            chat_type=ChatType.GROUP,
            description=data.description,
            owner_id=owner_id,
        )

        await self.repo.add_member(
            chat_id=chat.id,
            user_id=owner_id,
            role=ChatMemberRole.ADMIN,
        )

        for user_id in data.member_ids:
            if user_id == owner_id:
                continue
            await self.repo.add_member(
                chat_id=chat.id,
                user_id=user_id,
                role=ChatMemberRole.MEMBER,
            )

        await self.db.commit()
        await self.db.refresh(chat)
        return chat

    async def get_or_create_private_chat(
            self,
            current_user_id: int,
            data: CreatePrivateChatSchema,
    ):
        if current_user_id == data.target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O'zingiz bilan chat ocholmaysiz",
            )

        key = _make_direct_key(current_user_id, data.target_user_id)

        existing = await self.repo.get_by_direct_key(key)
        if existing:
            return existing

        chat = await self.repo.create_chat(
            name="",
            chat_type=ChatType.PRIVATE,
            owner_id=current_user_id,
            direct_key=key,
        )

        await self.repo.add_member(chat.id, current_user_id, ChatMemberRole.MEMBER)
        await self.repo.add_member(chat.id, data.target_user_id, ChatMemberRole.MEMBER)

        await self.db.commit()
        await self.db.refresh(chat)
        return chat

    async def leave_group(self, chat_id: int, user_id: int):
        chat = await self.repo.get_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat topilmadi")

        if chat.chat_type != ChatType.GROUP:
            raise HTTPException(status_code=400, detail="Bu guruh emas")

        removed = await self.repo.remove_member(chat_id, user_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Siz bu guruhda emassiz")

        await self.db.commit()

    async def get_chat_list(self, current_user_id: int, limit: int = 30, offset: int = 0) -> ChatListOut:
        rows = await self.repo.get_user_chats(
            user_id=current_user_id,
            limit=limit,
            offset=offset,
        )

        chats = [row[0] for row in rows]
        chat_ids = [chat.id for chat in chats]
        cursors = await self.repo.get_read_cursors(chat_ids, current_user_id)
        unread_counts = await self.message_repo.get_unread_counts(
            cursors=cursors,
            current_user_id=current_user_id,
        )

        private_users = await self.repo.get_private_chat_other_users(
            chat_ids=[
                chat.id for chat in chats
                if chat.chat_type == ChatType.PRIVATE
            ],
            current_user_id=current_user_id,
        )

        items = []

        for chat in chats:
            title = chat.name
            avatar = chat.avatar_url
            is_online = None
            last_seen = None

            if chat.chat_type == ChatType.PRIVATE:
                other_user = private_users.get(chat.id)

                if other_user:
                    title = f"{other_user.first_name} {other_user.last_name}"
                    avatar = other_user.profile_image
                    is_online = bool(await self.redis.exists(f"online:{other_user.id}"))

            last_message_out = None

            if chat.last_message_text:
                last_message_out = LastMessageOut(
                    id=getattr(chat, "last_message_id", None),
                    sender_id=chat.last_message_sender_id,
                    sender_name=None,
                    text=chat.last_message_text,
                    created_at=chat.last_message_created_at,
                )

            items.append(
                ChatListItemOut(
                    id=chat.id,
                    type=chat.chat_type.value.lower(),
                    title=title,
                    avatar=avatar,
                    is_online=is_online,
                    last_seen=last_seen,
                    last_message=last_message_out,
                    unread_count=unread_counts.get(chat.id, 0),
                    updated_at=chat.last_message_created_at,
                )
            )
        return ChatListOut(items=items)

    async def chat_detail(self, chat_id: int, current_user_id: int):
        return await self.repo.get_chat_detail_with_members(chat_id, current_user_id, self.redis)


def chat_service(
        db: AsyncSession = Depends(get_db),
        mongo_db: MongoDep = None,
) -> ChatService:
    return ChatService(db, mongo_db, redis_client)
