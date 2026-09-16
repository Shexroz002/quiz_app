from secrets import token_urlsafe

from sqlalchemy import select

from app.core.database.base import AsyncSessionLocal
from app.core.security.password_hash import hash_password
from app.models.account.user import User, UserType
from app.repositories.account import UserRepository
from app.repositories.account.user_subject_repo import UserSubjectRepository


class RegistrationConflictError(Exception):
    pass


async def get_user_by_telegram_id(telegram_id: int | str) -> User | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == str(telegram_id))
        )
        return result.scalar_one_or_none()


async def register_telegram_student(
    *,
    telegram_id: str,
    first_name: str,
    last_name: str,
    phone_number: str,
    subject_ids: list[int],
    profile_image: str | None = None,
) -> User:
    """Register (or link) the Telegram student and store the subjects they picked.

    ``education_level`` is left alone: the bot no longer asks for a grade, and an
    account linked by phone may already carry one set elsewhere.
    """
    async with AsyncSessionLocal() as db:
        existing_by_telegram = await db.execute(
            select(User).where(User.telegram_id == str(telegram_id))
        )
        user = existing_by_telegram.scalar_one_or_none()
        if user:
            return user

        existing_by_phone = await db.execute(
            select(User).where(User.phone_number == phone_number)
        )
        user = existing_by_phone.scalar_one_or_none()
        repo = UserRepository(db)
        if user:
            if user.telegram_id and user.telegram_id != str(telegram_id):
                raise RegistrationConflictError("Bu telefon raqam boshqa Telegram akkauntga ulangan.")

            user = await repo.update(
                user,
                {
                    "telegram_id": str(telegram_id),
                    "first_name": first_name or user.first_name,
                    "last_name": last_name or user.last_name,
                    "role": UserType.schoolboy,
                    "profile_image": profile_image or user.profile_image,
                },
                commit=False,
            )
            await UserSubjectRepository(db).create_or_update_subject(user.id, subject_ids)
            await db.commit()
            await db.refresh(user)
            return user

        user = await repo.create(
            {
                "username": f"tg_{telegram_id}",
                "telegram_id": str(telegram_id),
                "phone_number": phone_number,
                "first_name": first_name,
                "last_name": last_name,
                "password_hash": hash_password(token_urlsafe(32)),
                "role": UserType.schoolboy,
                "profile_image": profile_image,
            }
        )
        await db.flush()
        await UserSubjectRepository(db).create_or_update_subject(user.id, subject_ids)
        await db.commit()
        await db.refresh(user)
        return user
