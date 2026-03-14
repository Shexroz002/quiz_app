from sqlalchemy import select, case, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Contact, UserSubject
from app.models.account.user import User
from app.repositories.base.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):

    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def check_conflict(
            self,
            user_id: int,
            username: str
    ):
        stmt = select(User).where(
            and_(
                or_(User.username == username),
                User.id != user_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str):
        stmt = select(User).where(User.username == username)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def users_with_contact_status(
            self,
            current_user_id: int,
            search: str | None = None
    ):
        stmt = (
            select(
                User.id,
                User.username,
                User.first_name,
                User.last_name,
                User.profile_image,
                case(
                    (Contact.id != None, True),
                    else_=False
                ).label("contact_available")
            )
            .outerjoin(
                Contact,
                (Contact.friend_id == User.id) &
                (Contact.user_id == current_user_id)
            )
            .where(User.id != current_user_id)
        )

        if search:
            search_term = f"%{search}%"

            stmt = stmt.where(
                or_(
                    User.username.ilike(search_term),
                    User.first_name.ilike(search_term),
                    User.last_name.ilike(search_term),
                )
            )
        else:
            stmt = stmt.limit(10)

        result = await self.db.execute(stmt)

        return [
            {
                "id": r.id,
                "username": r.username,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "profile_image": r.profile_image,
                "contact_available": r.contact_available
            }
            for r in result
        ]

    async def user_full_information(self, user_id: int):
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.subjects).selectinload(UserSubject.subject)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_user_detail(self, user_id: int, data: dict) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        for field, value in data.items():
            setattr(user, field, value)

        await self.db.flush()
        return user
