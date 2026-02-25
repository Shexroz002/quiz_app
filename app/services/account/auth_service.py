import jwt
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database.base import get_db
from app.core.security.jwt import create_access_token
from app.core.security.password_hash import verify_password, hash_password
from app.repositories.account import UserRepository


class AuthService:

    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def login(self, username: str, password: str):

        user = await self.repo.get_by_username(username)

        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(401, "Invalid username or password")

        token = create_access_token(
            {"sub": str(user.username)}
        )

        return {
            "access_token": token,
            "token_type": "bearer"
        }

    async def register(self, schema):

        existing = await self.repo.get_by_username(
            schema.username
        )

        if existing:
            raise HTTPException(400, "Username already taken")

        user_data = {
            "username": schema.username,
            "first_name": schema.first_name,
            "last_name": schema.last_name,
            "password_hash": hash_password(schema.password),
        }

        try:
            user = await self.repo.create(user_data)
        except Exception:
            raise HTTPException(400, "Failed to register user")

        return {
            "msg": "User registered successfully",
            "user_id": user.id,
        }

    async def get_current_user(self, token: str):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username = payload.get("sub")
        except Exception:
            raise HTTPException(401, "Invalid token")

        user = await self.repo.get_by_username(username)

        if not user:
            raise HTTPException(401, "User not found")

        return user


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)
