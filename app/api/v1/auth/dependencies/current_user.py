from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from app.core.config import settings
from app.services.account.users import UserService, get_user_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/me")



async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(401, "Invalid token")
    user = await user_service.get(int(user_id))

    if not user:
        raise HTTPException(401, "User not found")
    return user
