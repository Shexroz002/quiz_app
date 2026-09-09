from secrets import token_urlsafe

from sqlalchemy import select

from app.core.database.base import AsyncSessionLocal
from app.core.security.password_hash import hash_password
from app.models.account.user import EducationLevel, User, UserType
from app.repositories.account import UserRepository


class RegistrationConflictError(Exception):
    pass


GRADE_TO_EDUCATION_LEVEL = {
    "5": EducationLevel.CLASS_5,
    "6": EducationLevel.CLASS_6,
    "7": EducationLevel.CLASS_7,
    "8": EducationLevel.CLASS_8,
    "9": EducationLevel.CLASS_9,
    "10": EducationLevel.CLASS_10,
    "11": EducationLevel.CLASS_11,
}


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
    grade: str,
    profile_image: str | None = None,
) -> User:
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
                    "education_level": GRADE_TO_EDUCATION_LEVEL[grade],
                    "profile_image": profile_image or user.profile_image,
                },
                commit=False,
            )
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
                "education_level": GRADE_TO_EDUCATION_LEVEL[grade],
                "profile_image": profile_image,
            }
        )
        await db.commit()
        await db.refresh(user)
        return user
