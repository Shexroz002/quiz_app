from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.models import User
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

    async def get_user_chats(self, user_id: int, limit: int = 30, offset: int = 0):
        stmt = (
            select(Chat, ChatMember)
            .join(ChatMember, ChatMember.chat_id == Chat.id)
            .where(ChatMember.user_id == user_id)
            .order_by(Chat.last_message_created_at.desc().nullslast(), Chat.id.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        return result.all()

    async def get_private_chat_other_users(self, chat_ids: list[int], current_user_id: int):
        if not chat_ids:
            return {}

        stmt = (
            select(ChatMember.chat_id, User)
            .join(User, User.id == ChatMember.user_id)
            .where(
                ChatMember.chat_id.in_(chat_ids),
                ChatMember.user_id != current_user_id,
            )
        )

        result = await self.db.execute(stmt)

        data = {}
        for chat_id, user in result.all():
            data[chat_id] = user

        return data

    async def get_read_cursors(self, chat_ids: list[int], user_id: int) -> dict[int, str | None]:
        stmt = (
            select(ChatMember.chat_id, ChatMember.last_read_message_id)
            .where(
                ChatMember.chat_id.in_(chat_ids),
                ChatMember.user_id == user_id,
            ))
        rows = await self.db.execute(stmt)
        return {chat_id: cursor for chat_id, cursor in rows.all()}

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

    async def update_chat_member_last_message_read_id(self, chat_id: int, user_id: int, message_id: str) -> bool:
        member = await self.get_member(chat_id, user_id)
        if not member:
            return False
        member.last_read_message_id = message_id
        await self.db.commit()
        return True

    async def get_chat_detail_with_members(self,chat_id: int,current_user_id: int,redis) -> dict | None:
        member_stmt = (
            select(ChatMember)
            .where(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == current_user_id,
            )
        )
        member_result = await self.db.execute(member_stmt)
        current_member = member_result.scalar_one_or_none()

        if not current_member:
            return None

        chat_stmt = select(Chat).where(Chat.id == chat_id)
        chat_result = await self.db.execute(chat_stmt)
        chat = chat_result.scalar_one_or_none()

        if not chat:
            return None

        members_stmt = (
            select(ChatMember, User)
            .join(User, User.id == ChatMember.user_id)
            .where(ChatMember.chat_id == chat_id)
            .order_by(ChatMember.joined_at.asc())
        )

        members_result = await self.db.execute(members_stmt)
        rows = members_result.all()

        members = []

        for chat_member, user in rows:
            is_online = bool(await redis.exists(f"online:{user.id}"))

            members.append({
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "profile_image": user.profile_image,
                "role": chat_member.role.value,
                "joined_at": chat_member.joined_at,
                "last_read_message_id": chat_member.last_read_message_id,
                "is_online": is_online,
            })

        return {
            "id": chat.id,
            "name": chat.name,
            "type": chat.chat_type.value.lower(),
            "description": chat.description,
            "avatar_url": chat.avatar_url,
            "owner_id": chat.owner_id,
            "direct_key": chat.direct_key,
            "last_message_text": chat.last_message_text,
            "last_message_sender_id": chat.last_message_sender_id,
            "last_message_created_at": chat.last_message_created_at,
            "members_count": len(members),
            "members": members,
        }
