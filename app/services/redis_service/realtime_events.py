import json
from typing import Any

from redis.asyncio import Redis


REALTIME_EVENTS_CHANNEL = "quiz:realtime_events"


async def publish_realtime_event(redis: Redis, event: dict[str, Any]) -> None:
    await redis.publish(REALTIME_EVENTS_CHANNEL, json.dumps(event, default=str))
