from fastapi import WebSocket
from starlette import status

from app.core.database.base import AsyncSessionLocal
from app.core.security.jwt import decode_token
from app.models import User
from app.repositories.account.user_repo import UserRepository

async def authenticate_websocket(websocket: WebSocket) -> User | None:

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token is required")
        return None

    payload = decode_token(token)
    user_id = payload.get("sub") if payload else None
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return None

    async with AsyncSessionLocal() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(int(user_id))
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not found")
            return None

        return user
