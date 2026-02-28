from fastapi import HTTPException, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.repositories.account import UserRepository
from app.services.base import BaseService


class UserService(BaseService):

    def __init__(self, db: AsyncSession):
        super().__init__(UserRepository(db))

    async def update_user(
            self,
            user_id: int,
            current_user,
            update_schema,
    ):
        if current_user.id != user_id:
            raise HTTPException(403, "Permission denied")

        user = await self.get(user_id)

        conflict = await self.repo.check_conflict(
            user_id,
            update_schema.username
        )

        if conflict:
            raise HTTPException(400, "Username or email exists")

        update_data = update_schema.model_dump(exclude_unset=True)

        return await self.repo.update(user, update_data)

    async def upload_avatar(self, user_id: int, avatar: UploadFile):
        user = await self.repo.get(user_id)

        if not user:
            raise HTTPException(404, "User not found")

        file_path = f"media/avatars/{user_id}_{avatar.filename}"

        with open(file_path, "wb") as buffer:
            buffer.write(await avatar.read())

        user.profile_image = file_path
        update_data = {
            "profile_image": file_path
        }
        await self.repo.update(user, update_data)

        return {"msg": "Avatar uploaded", "profile_image": file_path}

    async def get_by_username(self, username: str):
        return await self.repo.get_by_username(username)


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)
