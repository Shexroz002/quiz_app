from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.schemas.chat.message_schema import MessageCreate, MessageUpdate
from app.services.chat.exceptions import ChatAccessDeniedError, MessageNotFoundError
from app.services.chat.message_service import MessageService
from app.services.chat.real_time_event_service import RealTimeEventService

CREATED_AT = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
MESSAGE_ID = "507f1f77bcf86cd799439011"


def build_message_service(is_member: bool = True) -> MessageService:
    service = MessageService(MagicMock(), MagicMock())
    service.repo = AsyncMock()
    service.chat_repo = AsyncMock()
    service.chat_repo.is_member.return_value = is_member
    return service


def build_realtime_service(is_member: bool = True) -> RealTimeEventService:
    service = RealTimeEventService(MagicMock(), MagicMock(), AsyncMock(), AsyncMock())
    service.message_repo = AsyncMock()
    service.chat_repo = AsyncMock()
    service.chat_repo.is_member.return_value = is_member
    service.redis = AsyncMock()
    return service


class HttpMembershipTests(IsolatedAsyncioTestCase):
    async def test_send_message_rejects_non_member(self):
        service = build_message_service(is_member=False)
        data = MessageCreate(chat_id=5, sender_id=7, text="salom")

        with self.assertRaises(HTTPException) as ctx:
            await service.send_message(data, chat_id=5, sender_id=7)

        self.assertEqual(ctx.exception.status_code, 403)
        service.repo.create.assert_not_awaited()

    async def test_history_rejects_non_member(self):
        service = build_message_service(is_member=False)

        with self.assertRaises(HTTPException) as ctx:
            await service.get_history(chat_id=5, current_user_id=7)

        self.assertEqual(ctx.exception.status_code, 403)
        service.repo.get_chat_messages.assert_not_awaited()

    async def test_history_allows_member(self):
        service = build_message_service(is_member=True)
        service.repo.get_chat_messages.return_value = []

        await service.get_history(chat_id=5, current_user_id=7)

        service.chat_repo.is_member.assert_awaited_once_with(5, 7)
        service.repo.get_chat_messages.assert_awaited_once()

    async def test_view_message_rejects_non_member_of_message_chat(self):
        service = build_message_service(is_member=False)
        service.repo.get_by_id.return_value = {"_id": MESSAGE_ID, "chat_id": 42}

        with self.assertRaises(HTTPException) as ctx:
            await service.view_message(MESSAGE_ID, current_user_id=7)

        self.assertEqual(ctx.exception.status_code, 403)
        service.chat_repo.is_member.assert_awaited_once_with(42, 7)
        service.repo.increment_views.assert_not_awaited()

    async def test_missing_message_is_404_not_500(self):
        service = build_message_service()
        service.repo.get_by_id.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await service.view_message("not-an-object-id", current_user_id=7)

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_edit_by_non_owner_is_403_not_crash(self):
        service = build_message_service(is_member=True)
        service.repo.get_by_id.return_value = {"_id": MESSAGE_ID, "chat_id": 42}
        service.repo.update.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await service.edit_message(MESSAGE_ID, sender_id=7, data=MessageUpdate(text="x"))

        self.assertEqual(ctx.exception.status_code, 403)

    async def test_mark_as_read_rejects_foreign_chat(self):
        service = build_message_service()
        service.repo.get_chat_ids_for_messages.return_value = {1, 2}
        service.chat_repo.get_member_chat_ids.return_value = {1}

        with self.assertRaises(HTTPException) as ctx:
            await service.message_mark_as_read([MESSAGE_ID], current_user_id=7)

        self.assertEqual(ctx.exception.status_code, 403)
        service.repo.mark_as_read.assert_not_awaited()

    async def test_mark_as_read_allows_own_chats(self):
        service = build_message_service()
        service.repo.get_chat_ids_for_messages.return_value = {1, 2}
        service.chat_repo.get_member_chat_ids.return_value = {1, 2}

        await service.message_mark_as_read([MESSAGE_ID], current_user_id=7)

        service.repo.mark_as_read.assert_awaited_once_with([MESSAGE_ID])


class WebSocketMembershipTests(IsolatedAsyncioTestCase):
    async def test_message_new_rejects_non_member(self):
        service = build_realtime_service(is_member=False)

        with self.assertRaises(ChatAccessDeniedError):
            await service.message_new({"chat_id": 42, "text": "salom"}, sender_id=7)

        service.message_repo.create.assert_not_awaited()
        service.redis.publish.assert_not_awaited()

    async def test_message_new_publishes_for_member(self):
        service = build_realtime_service(is_member=True)
        service.message_repo.create.return_value = {
            "_id": MESSAGE_ID,
            "chat_id": 42,
            "sender_id": 7,
            "text": "salom",
            "created_at": CREATED_AT,
        }

        await service.message_new({"chat_id": 42, "text": "salom"}, sender_id=7)

        service.chat_repo.is_member.assert_awaited_once_with(42, 7)
        channel = service.redis.publish.await_args.args[0]
        self.assertEqual(channel, "chat:42")

    async def test_edit_publishes_to_real_chat_not_client_supplied(self):
        """Client soxta chat_id yuborsa ham event xabarning haqiqiy chatiga ketadi."""
        service = build_realtime_service(is_member=True)
        service.message_repo.get_by_id.return_value = {"_id": MESSAGE_ID, "chat_id": 42, "sender_id": 7}
        service.message_repo.update.return_value = {"text": "yangi", "mentions": [], "reply_to_message_id": None}

        await service.message_edit(
            {"message_id": MESSAGE_ID, "new_text": "yangi", "chat_id": 999},
            sender_id=7,
        )

        service.chat_repo.is_member.assert_awaited_once_with(42, 7)
        channel = service.redis.publish.await_args.args[0]
        self.assertEqual(channel, "chat:42")

    async def test_edit_by_non_owner_denied(self):
        service = build_realtime_service(is_member=True)
        service.message_repo.get_by_id.return_value = {"_id": MESSAGE_ID, "chat_id": 42, "sender_id": 9}
        service.message_repo.update.return_value = None

        with self.assertRaises(ChatAccessDeniedError):
            await service.message_edit({"message_id": MESSAGE_ID, "new_text": "x"}, sender_id=7)

        service.redis.publish.assert_not_awaited()

    async def test_forward_requires_access_to_source_chat(self):
        service = build_realtime_service()
        service.message_repo.get_by_id.return_value = {"_id": MESSAGE_ID, "chat_id": 99}
        # Manba chat (99) a'zosi emas, maqsad chat (42) a'zosi.
        service.chat_repo.is_member.side_effect = lambda chat_id, user_id: chat_id == 42

        with self.assertRaises(ChatAccessDeniedError):
            await service.forward_message(
                {"original_message_id": MESSAGE_ID, "chat_id": 42, "sender_name": "A"},
                sender_id=7,
            )

        service.message_repo.forward_message.assert_not_awaited()

    async def test_typing_rejects_non_member(self):
        service = build_realtime_service(is_member=False)

        with self.assertRaises(ChatAccessDeniedError):
            await service.typing_update({"chat_id": 42}, sender_id=7)

        service.redis.publish.assert_not_awaited()

    async def test_malformed_chat_id_denied_not_crash(self):
        """Noto'g'ri chat_id ValueError bilan ulanishni uzmasligi kerak."""
        service = build_realtime_service()

        for bad in ("abc", None, {"x": 1}):
            with self.subTest(chat_id=bad):
                with self.assertRaises(ChatAccessDeniedError):
                    await service.typing_update({"chat_id": bad}, sender_id=7)

    async def test_unknown_message_raises_not_found(self):
        service = build_realtime_service()
        service.message_repo.get_by_id.return_value = None

        with self.assertRaises(MessageNotFoundError):
            await service.message_reaction_add(
                {"message_id": MESSAGE_ID, "emoji": "👍"}, sender_id=7
            )
