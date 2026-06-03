import json

from fastapi.websockets import WebSocketDisconnect, WebSocket

from app.core.database.base import AsyncSessionLocal
from app.core.database.mongodb import get_mongo_db_to_method
from app.services.chat.real_time_event_service import RealTimeEventService
from app.websocket.chat.utils.event_type import EventType
from app.websocket.chat.utils.presence import now_iso

import asyncio
import json
import logging
from redis.exceptions import ConnectionError, TimeoutError

logger = logging.getLogger(__name__)


def _build_event(channel: str, payload: dict) -> dict:
    if channel.startswith("chat:"):
        return {
            "type": "message:new",
            "chat_id": channel.removeprefix("chat:"),
            **payload
        }

    if channel.startswith("presence:"):
        return {
            "type": "presence:update",
            "user_id": channel.removeprefix("presence:"),
            **payload
        }

    return payload


async def _redis_to_client(pubsub, ws, user_id: int):
    """Redis event stream -> WebSocket (stable version)"""

    try:
        while True:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )

                if message is None:
                    await asyncio.sleep(0.01)
                    continue

                print("Received from Redis:", message)

                # validate type
                if message.get("type") != "message":
                    continue

                channel = message.get("channel")
                raw_data = message.get("data")

                if not channel or not raw_data:
                    continue

                # JSON parse safe
                try:
                    payload = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    continue

                if payload.get("sender_id") == int(user_id):
                    continue

                # build event
                event = _build_event(channel, payload)

                # WebSocket disconnect safe send
                await ws.send_json(event)

            except (ConnectionError, TimeoutError) as e:
                logger.warning(f"Redis connection issue: {e}")
                await asyncio.sleep(1)

            except Exception as e:
                logger.exception(f"Redis stream error: {e}")
                await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        logger.info("Redis listener cancelled")
        raise

    finally:
        try:
            await pubsub.close()
        except Exception:
            pass


async def _client_to_server(ws: WebSocket, user_id: int, redis, pubsub):
    mongo_db = get_mongo_db_to_method()
    async with AsyncSessionLocal() as db:
        real_time_event = RealTimeEventService(mongo_db, db, redis, pubsub)
        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type")
                if msg_type == EventType.MESSAGE_NEW:
                    await real_time_event.message_new(msg, sender_id=user_id)

                if msg_type == EventType.MESSAGE_EDITED:
                    await real_time_event.message_edit(msg, sender_id=user_id)

                if msg_type == EventType.MESSAGE_DELETED:
                    await real_time_event.message_deleted(msg, sender_id=user_id)

                if msg_type == EventType.MESSAGE_REACTION_ADD:
                    await real_time_event.message_reaction_add(msg, sender_id=user_id)

                if msg_type == EventType.MESSAGE_READ:
                    await real_time_event.message_mark_as_read(msg, sender_id=user_id)

                elif msg_type == EventType.TYPING_UPDATE:
                    await real_time_event.typing_update(msg, int(user_id))

                elif msg_type == EventType.HEARTBEAT:
                    # Heartbeat - presence TTL ni yangilaymiz
                    await redis.setex(f"online:{user_id}", 60, "1")

                elif msg_type == EventType.CHAT_CREATED:
                    # Yangi chatga qo'shilish - dinamik subscribe
                    chat_id = msg["chat_id"]
                    await pubsub.subscribe(f"chat:{chat_id}")

                elif msg_type == EventType.CHAT_LEAVED:
                    chat_id = msg["chat_id"]
                    await pubsub.unsubscribe(f"chat:{chat_id}")

        except WebSocketDisconnect:
            return


async def set_user_online(redis, user_id: str, online: bool):
    if online:
        await redis.setex(f"online:{user_id}", 60, "1")
        status = "online"
    else:
        await redis.delete(f"online:{user_id}")
        status = "offline"

    payload = json.dumps({"status": status, "last_seen_at": now_iso()})
    await redis.publish(f"presence:{user_id}", payload)
