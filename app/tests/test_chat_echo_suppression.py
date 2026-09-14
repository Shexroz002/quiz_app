import asyncio
import json
from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from app.services.chat.real_time_event_service import RealTimeEventService
from app.websocket.chat.utils.chat_ws import _redis_to_client
from app.websocket.chat.utils.event_type import EventType

CREATED_AT = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
MESSAGE_ID = "507f1f77bcf86cd799439011"
MY_ORIGIN = "conn-aaa"
OTHER_ORIGIN = "conn-bbb"


class FakePubSub:
    """Berilgan xabarlarni qaytaradi, tugagach loopni CancelledError bilan to'xtatadi."""

    def __init__(self, messages):
        self._messages = list(messages)
        self.closed = False

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if self._messages:
            return self._messages.pop(0)
        raise asyncio.CancelledError

    async def close(self):
        self.closed = True


def redis_message(payload: dict, channel: str = "chat:1") -> dict:
    return {"type": "message", "channel": channel, "data": json.dumps(payload)}


def build_service(origin_id=MY_ORIGIN) -> RealTimeEventService:
    service = RealTimeEventService(MagicMock(), MagicMock(), AsyncMock(), AsyncMock(), origin_id)
    service.message_repo = AsyncMock()
    service.chat_repo = AsyncMock()
    service.chat_repo.is_member.return_value = True
    service.redis = AsyncMock()
    return service


class RedisToClientFilterTests(IsolatedAsyncioTestCase):
    async def drain(self, payloads, user_id=7, origin_id=MY_ORIGIN, channel="chat:1"):
        ws = AsyncMock()
        pubsub = FakePubSub([redis_message(p, channel) for p in payloads])
        with self.assertRaises(asyncio.CancelledError):
            await _redis_to_client(pubsub, ws, user_id, origin_id)
        return [call.args[0] for call in ws.send_json.await_args_list]

    async def test_own_connection_event_is_suppressed(self):
        sent = await self.drain([
            {"type": EventType.MESSAGE_NEW, "origin": MY_ORIGIN,
             "chat_id": 1, "message": {"sender_id": 7}},
        ])
        self.assertEqual(sent, [])

    async def test_other_device_of_same_user_still_receives_event(self):
        """Ko'p qurilma: boshqa ulanishdan kelgan o'z xabarim bu qurilmaga yetishi kerak."""
        sent = await self.drain([
            {"type": EventType.MESSAGE_NEW, "origin": OTHER_ORIGIN,
             "chat_id": 1, "message": {"sender_id": 7}},
        ])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["type"], EventType.MESSAGE_NEW)

    async def test_other_user_event_is_delivered(self):
        sent = await self.drain([
            {"type": EventType.MESSAGE_NEW, "origin": OTHER_ORIGIN,
             "chat_id": 1, "message": {"sender_id": 9}},
        ])
        self.assertEqual(len(sent), 1)

    async def test_origin_is_stripped_before_reaching_client(self):
        sent = await self.drain([
            {"type": EventType.MESSAGE_NEW, "origin": OTHER_ORIGIN,
             "chat_id": 1, "message": {"sender_id": 9}},
        ])
        self.assertNotIn("origin", sent[0])

    async def test_own_typing_suppressed_on_every_device(self):
        sent = await self.drain([
            {"type": EventType.TYPING_UPDATE, "origin": OTHER_ORIGIN, "sender_id": 7},
        ])
        self.assertEqual(sent, [])

    async def test_other_user_typing_is_delivered(self):
        sent = await self.drain([
            {"type": EventType.TYPING_UPDATE, "origin": OTHER_ORIGIN, "sender_id": 9},
        ])
        self.assertEqual(len(sent), 1)

    async def test_payload_without_origin_is_delivered(self):
        """Worker/boshqa manbadan origin'siz kelgan event bloklanmasligi kerak."""
        sent = await self.drain([
            {"type": EventType.MESSAGE_NEW, "chat_id": 1, "message": {"sender_id": 9}},
        ])
        self.assertEqual(len(sent), 1)


class AckTests(IsolatedAsyncioTestCase):
    async def test_message_new_returns_ack_with_server_message_id(self):
        service = build_service()
        service.message_repo.create.return_value = {
            "_id": MESSAGE_ID, "chat_id": 42, "sender_id": 7,
            "text": "salom", "created_at": CREATED_AT,
        }

        ack = await service.message_new(
            {"chat_id": 42, "text": "salom", "client_message_id": "tmp-1"}, sender_id=7
        )

        self.assertEqual(ack["type"], EventType.MESSAGE_ACK)
        self.assertEqual(ack["message_id"], MESSAGE_ID)
        self.assertEqual(ack["chat_id"], 42)
        self.assertEqual(ack["client_message_id"], "tmp-1")

    async def test_published_payload_carries_origin(self):
        service = build_service()
        service.message_repo.create.return_value = {
            "_id": MESSAGE_ID, "chat_id": 42, "sender_id": 7,
            "text": "salom", "created_at": CREATED_AT,
        }

        await service.message_new({"chat_id": 42, "text": "salom"}, sender_id=7)

        published = json.loads(service.redis.publish.await_args.args[1])
        self.assertEqual(published["origin"], MY_ORIGIN)

    async def test_new_chat_ack_carries_created_chat_id(self):
        """Yangi private chatning id sini client faqat ack orqali biladi."""
        service = build_service()
        service.chat_repo.get_by_direct_key.return_value = None
        created_chat = MagicMock()
        created_chat.id = 77
        service.chat_repo.create_chat.return_value = created_chat
        service.db = AsyncMock()
        service.pubsub = AsyncMock()
        service.message_repo.create.return_value = {
            "_id": MESSAGE_ID, "chat_id": 77, "sender_id": 7,
            "text": "salom", "created_at": CREATED_AT,
        }

        ack = await service.new_chat(
            {"target_user_id": 9, "text": "salom"}, sender_id=7
        )

        self.assertEqual(ack["chat_id"], 77)
        self.assertEqual(ack["message_id"], MESSAGE_ID)
