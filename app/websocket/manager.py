import asyncio
import json
import uuid
from collections import defaultdict
from typing import Any

import redis.asyncio as redis
from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import settings

WORKER_ID = str(uuid.uuid4())
PUBSUB_CHANNEL_PREFIX = "quiz_session:"

redis_client_ws = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


class SessionConnectionManager:
    """Tracks WebSocket connections per quiz session with Redis Pub/Sub for multi-worker support."""

    def __init__(self, redis_client: redis.Redis) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._redis = redis_client
        self._pubsub = self._redis.pubsub()
        self._listener_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the Redis Pub/Sub listener. Call this on app startup."""
        self._listener_task = asyncio.create_task(self._pubsub_listener())

    async def stop(self) -> None:
        """Stop the Redis Pub/Sub listener. Call this on app shutdown."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        await self._pubsub.close()

    def _channel(self, session_id: int) -> str:
        return f"{PUBSUB_CHANNEL_PREFIX}{session_id}"

    async def connect(self, websocket: WebSocket, session_id: int) -> None:
        await websocket.accept()
        self._connections[session_id].add(websocket)

        # Subscribe to this session's Redis channel (idempotent)
        await self._pubsub.subscribe(self._channel(session_id))

        # Register this worker as active for the session
        await self._redis.sadd(f"session_workers:{session_id}", WORKER_ID)

    def disconnect(self, websocket: WebSocket, session_id: int) -> None:
        connections = self._connections.get(session_id)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(session_id, None)
            # Schedule async cleanup without blocking
            asyncio.create_task(self._cleanup_session(session_id))

    async def _cleanup_session(self, session_id: int) -> None:
        """Unsubscribe and remove worker from Redis when no local connections remain."""
        await self._pubsub.unsubscribe(self._channel(session_id))
        await self._redis.srem(f"session_workers:{session_id}", WORKER_ID)

    def count(self, session_id: int) -> int:
        return len(self._connections.get(session_id, set()))

    async def broadcast(
            self,
            session_id: int,
            event: str,
            payload: dict[str, Any] | None = None,
    ) -> None:
        """Publish to Redis — all workers (including this one) receive it via Pub/Sub."""
        message = json.dumps({"event": event, "data": payload or {}})
        await self._redis.publish(self._channel(session_id), message)

    async def _broadcast_local(self, session_id: int, raw_message: str) -> None:
        """Send a raw JSON message to all local WebSocket connections for this session."""
        message = json.loads(raw_message)
        stale_connections: list[WebSocket] = []

        for connection in self._connections.get(session_id, set()):
            try:
                await connection.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(connection, session_id)

    async def _pubsub_listener(self) -> None:
        """Listen for Redis Pub/Sub messages and deliver them to local WebSocket clients."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                channel: str = message["channel"]
                if not channel.startswith(PUBSUB_CHANNEL_PREFIX):
                    continue
                session_id = int(channel.removeprefix(PUBSUB_CHANNEL_PREFIX))
                await self._broadcast_local(session_id, message["data"])
        except asyncio.CancelledError:
            pass


session_ws_manager = SessionConnectionManager(redis_client_ws)
