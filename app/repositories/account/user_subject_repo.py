from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserSubject
from app.repositories.base.base_repository import BaseRepository


class UserSubjectRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(UserSubject, db)

    async def create_user_subjects(self, data: list[UserSubject]) -> list[UserSubject]:
        self.db.add_all(data)
        await self.db.flush()
        return data

    async def create_or_update_subject(self, user_id: int, subject_id_list: list[int]) -> None:

        exist_subjects_id = await self.db.execute(
            select(UserSubject.subject_id).where(UserSubject.user_id == user_id)
        )
        exist_subjects_id = set(exist_subjects_id.scalars().all())
        deleted_subjects_ids = exist_subjects_id - set(subject_id_list)
        new_subjects_ids = set(subject_id_list) - exist_subjects_id

        for subject_id in new_subjects_ids:
            stmt = select(self.model).where(
                self.model.user_id == user_id,
                self.model.subject_id == subject_id,
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                continue

            user_subject = self.model(
                user_id=user_id,
                subject_id=subject_id,
            )
            self.db.add(user_subject)
            await self.db.flush()
            await self.db.refresh(user_subject)

        if deleted_subjects_ids:
            if deleted_subjects_ids:
                stmt = delete(self.model).where(
                    self.model.user_id == user_id,
                    self.model.subject_id.in_(deleted_subjects_ids)
                )
                await self.db.execute(stmt)
            await self.db.flush()
        return None
