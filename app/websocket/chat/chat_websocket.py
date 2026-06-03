import asyncio

from fastapi import APIRouter
from fastapi.websockets import WebSocket

from app.core.config import settings
from app.core.database.session import AsyncSessionLocal
from app.websocket.chat.chat_ws_manager import chat_manager
from app.websocket.utils import authenticate_websocket
from app.websocket.chat.utils.chat_ws import _client_to_server, _redis_to_client
from app.websocket.chat.utils.presence import set_user_online, get_user_friend_ids, get_user_chat_ids
import redis.asyncio as redis

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
chat_ws_router = APIRouter(tags=["Chat WebSocket"])


@chat_ws_router.websocket("/ws/chat")
async def websocket_endpoint(ws: WebSocket):
    user = await authenticate_websocket(ws)
    if not user:
        await ws.close(code=1008)
        return
    user_id = user.id
    await chat_manager.connect(user_id, ws)

    async with AsyncSessionLocal() as session:
        chat_ids = await get_user_chat_ids(session, user_id)
        friend_ids = await get_user_friend_ids(session, user_id)

    user_id = int(user.id)
    channels = (
            [f"chat:{cid}" for cid in chat_ids] +
            [f"presence:{fid}" for fid in friend_ids] +
            [f"user:{user.id}"]
    )
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(*channels)
    await set_user_online(redis_client, user_id, online=True)

    await ws.send_json({"type": "connection:ready", "subscribed_channels": len(channels)})

    redis_task = asyncio.create_task(_redis_to_client(pubsub, ws, user_id))
    client_task = asyncio.create_task(_client_to_server(ws, user_id, redis_client, pubsub))

    try:

        done, pending = await asyncio.wait(
            [redis_task, client_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        try:
            await pubsub.aclose()
        except Exception:
            pass

        chat_manager.disconnect(user_id, ws)
        if not chat_manager.is_online(user_id):
            try:
                await set_user_online(redis_client, user_id, online=False)
            except Exception:

                pass
