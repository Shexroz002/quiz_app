from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from app.repositories.chat.chat_repo import ChatRepository
from app.repositories.chat.presence_repository import PresenceRepository


def user(uid, first="A", last="B"):
    return SimpleNamespace(id=uid, username=f"u{uid}", first_name=first, last_name=last,
                           profile_image=None)


class PresenceKeyTests(IsolatedAsyncioTestCase):
    """Presence "online:{id}" kalitiga yoziladi; "presence:{id}" - bu pub/sub kanali."""

    async def test_is_online_reads_online_key(self):
        redis = AsyncMock()
        redis.exists.return_value = 1

        result = await PresenceRepository(redis).is_online(7)

        self.assertTrue(result)
        redis.exists.assert_awaited_once_with("online:7")

    async def test_is_online_bulk_reads_online_keys(self):
        redis = AsyncMock()
        redis.mget.return_value = ["1", None]

        result = await PresenceRepository(redis).is_online_bulk([7, 9])

        redis.mget.assert_awaited_once_with(["online:7", "online:9"])
        self.assertEqual(result, {7: True, 9: False})

    async def test_bulk_uses_single_round_trip(self):
        redis = AsyncMock()
        redis.mget.return_value = [None] * 50

        await PresenceRepository(redis).is_online_bulk(list(range(50)))

        self.assertEqual(redis.mget.await_count, 1)
        redis.exists.assert_not_awaited()

    async def test_last_seen_bulk_reads_last_seen_keys(self):
        redis = AsyncMock()
        redis.mget.return_value = ["2026-09-14T10:00:00+00:00", None]

        result = await PresenceRepository(redis).get_last_seen_bulk([7, 9])

        redis.mget.assert_awaited_once_with(["last_seen:7", "last_seen:9"])
        self.assertEqual(result[7], "2026-09-14T10:00:00+00:00")
        self.assertIsNone(result[9])

    async def test_empty_input_makes_no_redis_call(self):
        redis = AsyncMock()
        repo = PresenceRepository(redis)

        self.assertEqual(await repo.is_online_bulk([]), {})
        self.assertEqual(await repo.get_last_seen_bulk([]), {})
        redis.mget.assert_not_awaited()


class ChatDetailPresenceTests(IsolatedAsyncioTestCase):
    async def test_members_presence_uses_one_bulk_call(self):
        repo = ChatRepository(MagicMock())
        members = [(SimpleNamespace(role=MagicMock(value="member"),
                                    joined_at=None, last_read_message_id=None), user(uid))
                   for uid in (1, 2, 3)]

        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=MagicMock())),   # current member
            MagicMock(scalar_one_or_none=MagicMock(return_value=SimpleNamespace(
                id=1, name="G", chat_type=MagicMock(value="GROUP"), description=None,
                avatar_url=None, owner_id=1, direct_key=None, last_message_text=None,
                last_message_sender_id=None, last_message_created_at=None))),     # chat
            MagicMock(all=MagicMock(return_value=members)),                       # members
        ]
        repo.db.execute = AsyncMock(side_effect=results)

        presence_repo = AsyncMock()
        presence_repo.is_online_bulk.return_value = {1: True, 2: False, 3: True}

        detail = await repo.get_chat_detail_with_members(1, 1, presence_repo)

        presence_repo.is_online_bulk.assert_awaited_once_with([1, 2, 3])
        self.assertEqual([m["is_online"] for m in detail["members"]], [True, False, True])
