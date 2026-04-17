import os
import uuid

from fastapi import HTTPException, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database.base import get_db
from app.repositories.account import UserRepository, UserSubjectRepository
from app.services.base import BaseService
from app.services.pdf.storage_service import StorageService


class UserService(BaseService):

    def __init__(self, db: AsyncSession, file_storage: StorageService):
        super().__init__(UserRepository(db))
        self.user_subject_repo = UserSubjectRepository(db)
        self.db = db
        self.storage = file_storage

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
            raise HTTPException(status_code=404, detail="User not found")

        allowed_types = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }

        if avatar.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Only jpg, png, webp allowed")

        ext = allowed_types[avatar.content_type]
        job_id = uuid.uuid4()
        file_name = f"{job_id}{ext}"
        file_path = os.path.join(self.storage.upload_dir, file_name)

        await self.storage.save_pdf(avatar, file_path)

        db_path = f"{settings.AVATAR_DIR}/{file_name}"
        await self.repo.update(user, {"profile_image": db_path})

        return {
            "msg": "Avatar uploaded",
            "profile_image": db_path,
        }

    async def get_by_username(self, username: str):
        return await self.repo.get_by_username(username)

    async def search_users_for_contact(self, current_user_id: int, search: str = None):
        return await self.repo.users_with_contact_status(current_user_id=current_user_id, search=search)


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    storage = StorageService(
        upload_dir=settings.AVATAR_DIR,
        max_size_bytes=settings.MAX_PDF_SIZE,
    )
    return UserService(db, storage)
