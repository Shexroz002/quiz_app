import asyncio
import json
import logging

from app.core.database.redis import redis_client
from app.services.redis_service.realtime_events import REALTIME_EVENTS_CHANNEL
from app.websocket.manager import session_ws_manager
from app.websocket.notification_manager import notification_manager
from app.websocket.session_monitoring_ws_manager import session_monitoring_ws_manager


logger = logging.getLogger(__name__)


async def _dispatch_event(event: dict) -> None:
    target = event.get("target")
    if target == "notification":
        await notification_manager.send_to_user(
            user_id=int(event["user_id"]),
            notification_type=event["notification_type"],
            payload=event.get("payload"),
            unread_count=event.get("unread_count"),
        )
    elif target == "session":
        session_id = int(event["session_id"])
        name = event["event"]
        payload = event.get("payload") or {}
        await session_ws_manager.broadcast(session_id, name, payload)
        await session_monitoring_ws_manager.broadcast(session_id, name, payload)


async def consume_realtime_events() -> None:
    while True:
        pubsub = redis_client.pubsub()
        try:
            await pubsub.subscribe(REALTIME_EVENTS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                await _dispatch_event(json.loads(message["data"]))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Redis real-time event consumer failed")
            await asyncio.sleep(1)
        finally:
            await pubsub.aclose()
