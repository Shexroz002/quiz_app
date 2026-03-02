from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.database.base import get_db
from app.repositories.account import ContactRepository, UserRepository


class ContactService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ContactRepository(db)
        self.user_repo = UserRepository(db)

    async def create_contact(self, friend_id: int, contact_user_id: int, name: str = None):
        if friend_id == contact_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot add yourself as a contact.")

        contact = await self.repo.get_contact_by_id(friend_id, contact_user_id)
        if contact:
            return contact

        friend = await self.user_repo.get_by_id(friend_id)
        if not friend:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend not found.")
        if name is None:
            if friend.first_name and friend.last_name:
                name = f"{friend.first_name} {friend.last_name}"
            else:
                name = friend.username
        data = {
            "friend_id": friend_id,
            "user_id": contact_user_id,
            "name": name
        }
        data = await self.repo.create(data)
        await self.db.commit()
        return data

    async def contact_list(self, contact_user_id: int):
        return await self.repo.contact_list(contact_user_id)


def get_contact_service(db: AsyncSession = Depends(get_db)) -> ContactService:
    return ContactService(db)
