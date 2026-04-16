from fastapi import HTTPException, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import os
import shutil
from pathlib import Path
from app.core.database.base import get_db
from app.repositories.account import UserRepository, UserSubjectRepository
from app.services.base import BaseService


class UserService(BaseService):

    def __init__(self, db: AsyncSession):
        super().__init__(UserRepository(db))
        self.user_subject_repo = UserSubjectRepository(db)
        self.db = db

    async def update_user(
            self,
            user_id: int,
            current_user,
            update_schema,
    ):
        if current_user.id != user_id:
            raise HTTPException(403, "Permission denied")

        user = await self.get(user_id)
        subject_ids = update_schema.subject_ids
        if subject_ids:
            await self.user_subject_repo.create_or_update_subject(user.id, subject_ids)

        update_data = update_schema.model_dump(exclude_unset=True)
        user_update_data = await self.repo.update(user, update_data)
        await self.db.commit()
        return user_update_data

    async def upload_avatar(self, user_id: int, avatar: UploadFile):
        user = await self.repo.get(user_id)

        if not user:
            raise HTTPException(404, "User not found")

        # Faqat rasm formatlarini qabul qilish
        allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
        if avatar.content_type not in allowed_types:
            raise HTTPException(400, "Faqat rasm fayllari qabul qilinadi")

        # Papkani yaratish (mavjud bo'lmasa)
        upload_dir = Path("media/avatars")
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = str(upload_dir / f"{user_id}_{avatar.filename}")

        # Faylni to'g'ri saqlash
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(avatar.file, buffer)

        update_data = {
            "profile_image": file_path
        }
        await self.repo.update(user, update_data)

        return {"msg": "Avatar uploaded", "profile_image": file_path}

    async def get_by_username(self, username: str):
        return await self.repo.get_by_username(username)

    async def search_users_for_contact(self, current_user_id: int, search: str = None):
        return await self.repo.users_with_contact_status(current_user_id=current_user_id, search=search)


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)
