from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.chat.chat_members import ChatMember, ChatMemberRole
from app.models.chat.chats import Chat


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, chat_id: int) -> Chat | None:
        result = await self.db.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        return result.scalar_one_or_none()


    async def get_by_direct_key(self, key: str) -> Chat | None:
        result = await self.db.execute(
            select(Chat).where(Chat.direct_key == key)
        )
        return result.scalar_one_or_none()


    async def get_member(self, chat_id: int, user_id: int) -> ChatMember | None:
        result = await self.db.execute(
            select(ChatMember).where(
                and_(
                    ChatMember.chat_id == chat_id,
                    ChatMember.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()


    async def get_user_chats(self, user_id: int) -> list[Chat]:
        result = await self.db.execute(
            select(Chat)
            .join(ChatMember, ChatMember.chat_id == Chat.id)
            .where(ChatMember.user_id == user_id)
            .order_by(Chat.last_message_created_at.desc().nullslast())
        )
        return list(result.scalars().all())


    async def create_chat(self, **kwargs) -> Chat:
        chat = Chat(**kwargs)
        self.db.add(chat)
        await self.db.flush()
        return chat


    async def add_member(
            self,
            chat_id: int,
            user_id: int,
            role: ChatMemberRole = ChatMemberRole.MEMBER,
    ) -> ChatMember:
        member = ChatMember(chat_id=chat_id, user_id=user_id, role=role)
        self.db.add(member)
        await self.db.flush()
        return member


    async def remove_member(self, chat_id: int, user_id: int) -> bool:
        member = await self.get_member(chat_id, user_id)
        if not member:
            return False
        await self.db.delete(member)
        return True


    async def update_chat_last_message(self, chat_id: int, message_text: str, sender_id: int,
                                       created_at: datetime) -> Chat | None:
        chat = await self.get_by_id(chat_id)
        if not chat:
            return None
        chat.last_message_text = message_text
        chat.last_message_sender_id = sender_id
        chat.last_message_created_at = created_at
        await self.db.commit()
        return chat
