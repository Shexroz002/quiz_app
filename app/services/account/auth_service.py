import jwt
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import settings
from app.core.database.base import get_db
from app.core.security.jwt import create_access_token, create_refresh_token
from app.core.security.password_hash import verify_password, hash_password
from app.models import UserSubject
from app.models.account.user import UserType
from app.repositories.account import UserRepository
from app.repositories.account import UserSubjectRepository


class AuthService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)
        self.user_subject_repo = UserSubjectRepository(db)

    async def login(self, username: str, password: str):
        user = await self.repo.get_by_username(username)

        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        subject = str(user.id)
        return {
            "access_token": create_access_token(subject),
            "refresh_token": create_refresh_token(subject),
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "image_url": user.profile_image  if user.profile_image else None,
            },
        }

    async def refresh(self,refresh_token: str):
        try:
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid token type")
            subject = payload.get("sub")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        user = await self.repo.get_by_id(int(subject))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return {
            "access_token": create_access_token(subject),
            "refresh_token": create_refresh_token(subject),
            "token_type": "bearer",
        }

    async def register(self, schema):

        existing = await self.repo.get_by_username(schema.username)

        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")

        try:
            role_value = UserType(schema.role) if schema.role else UserType.student
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid role type")

        user_data = {
            "username": schema.username,
            "first_name": schema.first_name,
            "last_name": schema.last_name,
            "password_hash": hash_password(schema.password),
            "role": role_value,
        }

        subjects = schema.subjects

        try:
            user = await self.repo.create(user_data)

            if subjects:
                user_subject_data = [
                    UserSubject(user_id=user.id, subject_id=subject.id)
                    for subject in subjects
                ]

                await self.user_subject_repo.create_user_subjects(user_subject_data)
            await self.db.commit()

            return user

        except Exception as e:
            await self.db.rollback()
            raise HTTPException(400, f"Failed to register user: {str(e)}")

    async def get_user_by_id(self, user_id: int):
        user = await self.repo.get_by_id(user_id)

        if not user:
            raise HTTPException(401, "User not found")

        return user


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)
