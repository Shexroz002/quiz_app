from uuid import uuid4

from fastapi import HTTPException, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import time
import random
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
            raise HTTPException(status_code=404, detail="User not found")

        allowed_types = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
        if avatar.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Only jpg, png, webp allowed")

        upload_dir = Path("/home/quiz_app/media/avatars")
        upload_dir.mkdir(parents=True, exist_ok=True)

        ext = allowed_types[avatar.content_type]
        filename = f"{user_id}_{uuid4().hex}{ext}"
        file_path = upload_dir / filename

        content = await avatar.read()
        with open(file_path, "wb") as f:
            f.write(content)

        profile_image = f"/media/avatars/{filename}"

        await self.repo.update(user, {"profile_image": profile_image})

        return {
            "msg": "Avatar uploaded",
            "profile_image": profile_image,
        }

    async def get_by_username(self, username: str):
        return await self.repo.get_by_username(username)

    async def search_users_for_contact(self, current_user_id: int, search: str = None):
        return await self.repo.users_with_contact_status(current_user_id=current_user_id, search=search)


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)
