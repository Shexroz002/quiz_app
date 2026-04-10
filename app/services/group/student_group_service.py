from typing import Any

from fastapi import Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.models import Contact
from app.models.group.student_group import StudentGroup
from app.repositories.group.student_group_repository import StudentGroupRepository
from app.schemas.group.student_group import StudentGroupCreateSchema, StudentGroupUpdateSchema


class StudentGroupService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StudentGroupRepository(db)

    async def create_group(self, teacher_id: int, data: StudentGroupCreateSchema,
                           cover_image: UploadFile | None = None, ):
        cover_image_path = None

        if cover_image:
            cover_image_path = await self.upload_image(teacher_id, cover_image)

        group = StudentGroup(
            teacher_id=teacher_id,
            name=data.name,
            subject_id=data.subject_id,
            color=data.color,
            description=data.description,
            cover_image=cover_image_path,

        )

        group = await self.repo.create_group(group)
        if data.student_ids:
            await self.repo.add_members(group.id, data.student_ids, teacher_id)

        await self.db.commit()
        return group

    async def update_group(
            self,
            group_id: int,
            teacher_id: int,
            data: StudentGroupUpdateSchema,
    ):
        group = await self.repo.get_group(group_id)
        if not group:
            raise ValueError("Group not found")

        if group.teacher_id != teacher_id:
            raise ValueError("Permission denied")

        update_data = data.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            setattr(group, key, value)

        await self.db.commit()
        return group

    async def remove_members(self, group_id: int, teacher_id: int, student_ids: list[int]):
        group = await self.repo.get_group(group_id)
        if not group:
            raise ValueError("Group not found")
        if group.teacher_id != teacher_id:
            raise ValueError("Permission denied")

        await self.repo.remove_members(group_id, student_ids)
        await self.db.commit()
        return group

    async def group_members(self, group_id: int, teacher_id: int, search: str | None = None):
        group = await self.repo.get_group(group_id)
        if not group:
            raise ValueError("Group not found")
        if group.teacher_id != teacher_id:
            raise ValueError("Permission denied")
        return await self.repo.group_members(group_id, search)

    async def add_members(self, group_id: int, teacher_id: int, student_ids: list[int]):
        group = await self.repo.get_group(group_id)
        if not group:
            raise ValueError("Group not found")
        if group.teacher_id != teacher_id:
            raise ValueError("Permission denied")
        await self.repo.add_members(group_id, student_ids, teacher_id)
        await self.db.commit()
        return group

    async def list_groups(self, teacher_id: int, search: str | None = None, subject_id: int | None = None):
        return await self.repo.list_groups(teacher_id, search, subject_id)

    async def group_short_info(self,teacher_id:int):
        return await self.repo.list_groups_short_info(teacher_id)

    @staticmethod
    async def upload_image(teacher_id: int, image: UploadFile):

        file_path = f"media/avatars/{teacher_id}_{image.filename}"

        with open(file_path, "wb") as buffer:
            buffer.write(await image.read())

        return file_path

    async def update_group_image(self, group_id: int, teacher_id: int, image: UploadFile) -> str | None:
        group = await self.repo.get_group(group_id)
        cover_image_path = None
        if not group:
            raise ValueError("Group not found")
        if group.teacher_id != teacher_id:
            raise ValueError("Permission denied")

        if image:
            cover_image_path = await self.upload_image(teacher_id, image)
            group.cover_image = cover_image_path
            await self.db.commit()
        return cover_image_path

    async def delete_group_image(self, group_id: int, teacher_id: int) -> None:
        group = await self.repo.get_group(group_id)
        if not group:
            raise ValueError("Group not found")
        if group.teacher_id != teacher_id:
            raise ValueError("Permission denied")

        group.cover_image = None
        await self.db.commit()

        return None

    async def get_group_detail_card(self, group_id: int, teacher_id: int, ):
        return await self.repo.get_group_detail_card(group_id=group_id, teacher_id=teacher_id, )

    async def get_group_students_performance(self, group_id: int, teacher_id: int, search: str | None = None, ):
        return await self.repo.get_group_students_performance(group_id=group_id, teacher_id=teacher_id, search=search)

    async def get_group_test_results(self, group_id: int, teacher_id: int, ):
        return await self.repo.get_group_test_results(group_id=group_id, teacher_id=teacher_id)

    async def list_groups_by_member_id(self, member_id: int, search: str | None = None, subject_id: int | None = None):
        return await self.repo.list_groups(None, search, subject_id, member_id)

    async def group_detail_card_for_student(self, group_id: int, member_id: int, ):
        if not await self.repo.is_group_member(group_id, member_id):
            raise ValueError("Permission denied")
        group = await self.repo.get_group(group_id)
        return await self.repo.get_group_detail_card(group_id=group_id, teacher_id=group.teacher_id)

    async def group_students_performance(self, group_id: int, member_id: int, search: str | None = None, ):
        if not await self.repo.is_group_member(group_id, member_id):
            raise ValueError("Permission denied")
        group = await self.repo.get_group(group_id)
        return await self.repo.get_group_students_performance(group_id=group_id, teacher_id=group.teacher_id, search=search)

    async def group_test_results(self, group_id: int, member_id: int, ):
        if not await self.repo.is_group_member(group_id, member_id):
            raise ValueError("Permission denied")
        group = await self.repo.get_group(group_id)
        return await self.repo.get_group_test_results(group_id=group_id, teacher_id=group.teacher_id)



def get_student_group_service(db: AsyncSession = Depends(get_db)) -> StudentGroupService:
    return StudentGroupService(db)
