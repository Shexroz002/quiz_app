from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Contact, User
from app.repositories.base.base_repository import BaseRepository


class ContactRepository(BaseRepository[Contact]):

    def __init__(self, db: AsyncSession):
        super().__init__(Contact, db)

    async def create_contact(self, user_id: int, friend_id: int, name: str ):
        stmt = select(Contact).where(Contact.user_id == user_id, Contact.friend_id == friend_id)
        result = await self.db.execute(stmt)
        existing_contact = result.scalar_one_or_none()
        if existing_contact:
            return existing_contact

        contact = Contact(user_id=user_id, friend_id=friend_id, name=name)
        self.db.add(contact)
        return contact

    async def contact_list(self, contact_user_id: int) -> Sequence[Contact]:
        stmt = select(Contact).options(selectinload(Contact.friend)).where(Contact.user_id == contact_user_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def contact_suggestions(self, contact_user_id: int) -> Sequence[User]:
        contacts = await self.contact_list(contact_user_id)
        contact_ids = {contact.friend_id for contact in contacts}
        stmt = select(User).where(~User.id.in_(contact_ids.union({contact_user_id}))).limit(10)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_contact_by_id(self, friend_id: int, contact_user_id: int) -> Contact:
        stmt = select(Contact).where(Contact.user_id == contact_user_id, Contact.friend_id == friend_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
