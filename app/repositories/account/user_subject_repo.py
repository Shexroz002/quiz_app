from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserSubject
from app.repositories.base.base_repository import BaseRepository


class UserSubjectRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(UserSubject, db)


    async def create_user_subjects(self,data:list[UserSubject]) -> list[UserSubject]:

        self.db.add_all(data)
        await self.db.flush()
        return data




