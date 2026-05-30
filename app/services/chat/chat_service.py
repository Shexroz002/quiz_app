from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.models.chat.chat_members import ChatMemberRole
from app.models.chat.chats import ChatType
from app.repositories.chat.chat_repo import ChatRepository
from app.schemas.chat.chat_schema import CreateGroupChatSchema, CreatePrivateChatSchema


def _make_direct_key(user1_id: int, user2_id: int) -> str:
    """Har doim kichik id:katta id tartibida"""
    a, b = sorted([user1_id, user2_id])
    return f"{a}:{b}"


class ChatService:
    def __init__(self, db: AsyncSession):
        self.repo = ChatRepository(db)
        self.db = db

    # ─── Group Chat ───────────────────────────────────────
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

        # Owner ni ADMIN sifatida qo'shish
        await self.repo.add_member(
            chat_id=chat.id,
            user_id=owner_id,
            role=ChatMemberRole.ADMIN,
        )

        # Qolgan a'zolarni qo'shish
        for user_id in data.member_ids:
            if user_id == owner_id:
                continue  # Ikki marta qo'shilmasin
            await self.repo.add_member(
                chat_id=chat.id,
                user_id=user_id,
                role=ChatMemberRole.MEMBER,
            )

        await self.db.commit()
        await self.db.refresh(chat)
        return chat

    # ─── Private (Direct) Chat ────────────────────────────
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


    async def get_my_chats(self, user_id: int):
        return await self.repo.get_user_chats(user_id)

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



def chat_service(db: AsyncSession = Depends(get_db)) -> ChatService:
    return ChatService(db)