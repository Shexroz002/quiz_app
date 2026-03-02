from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, User
from app.repositories.base.base_repository import BaseRepository


class ContactRepository(BaseRepository[Contact]):

    def __init__(self, db: AsyncSession):
        super().__init__(Contact, db)


    async  def contact_list(self, contact_user_id:int) -> Sequence[Contact]:
        stmt = select(Contact).where(Contact.user_id == contact_user_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_contact_by_id(self, friend_id:int, contact_user_id:int) -> Contact:
        stmt = select(Contact).where(Contact.user_id == contact_user_id, Contact.friend_id == friend_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

