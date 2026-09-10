from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest
from fastapi import HTTPException

from app.bot.handlers.quiz_room import start_room
from app.bot.keyboards.quiz_room import player_keyboard, room_keyboard
from app.bot.services.quiz_room import (
    create_room,
    format_group_leaderboard,
    format_host_waiting_room,
    format_leaderboard,
    format_private_running_room,
    format_room_join_confirmation,
    format_room_start_message,
    format_running_group_room,
    format_waiting_group_room,
    enter_room,
    publish_room,
    send_room_start_to_participants,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class TelegramQuizRoomDeliveryTests(IsolatedAsyncioTestCase):
    async def test_group_room_creation_sends_private_host_control(self):
        user = SimpleNamespace(id=22)
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            host_id=user.id,
            duration_minutes=15,
            max_participants=20,
        )
        quiz = SimpleNamespace(id=4, subject="Matematika", title="Algebra")
        service = SimpleNamespace(
            create_managed_session=AsyncMock(return_value=session),
            participant_repo=SimpleNamespace(
                get_participant_list=AsyncMock(return_value=[{"is_host": True}]),
            ),
            quiz_repo=SimpleNamespace(
                quiz_question_count=AsyncMock(return_value=30),
            ),
        )
        db = SimpleNamespace(
            execute=AsyncMock(side_effect=[
                _ScalarResult(None),
                _ScalarResult(None),
            ]),
            get=AsyncMock(return_value=quiz),
            add=lambda room: None,
            commit=AsyncMock(),
        )
        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username="example_bot")),
            send_message=AsyncMock(),
        )

        with (
            patch(
                "app.bot.services.quiz_room.registered_user",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "app.bot.services.quiz_room.AsyncSessionLocal",
                return_value=_SessionContext(db),
            ),
            patch(
                "app.bot.services.quiz_room.MultiplayerQuizService",
                return_value=service,
            ),
            patch(
                "app.bot.services.quiz_room.publish_room",
                new_callable=AsyncMock,
            ) as publish_room,
        ):
            await create_room(bot, 42, -100123, 555, 4, 15)

        publish_room.assert_awaited_once_with(bot, 12)
        bot.send_message.assert_awaited_once()
        sent = bot.send_message.await_args
        self.assertEqual(sent.kwargs["chat_id"], 42)
        self.assertIn("Test xonasi tayyor!", sent.kwargs["text"])
        self.assertIn("👥 1/20 ishtirokchi", sent.kwargs["text"])
        start_button = sent.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(start_button.callback_data, "room:start:12")

    async def test_duplicate_create_callback_reuses_durable_room(self):
        user = SimpleNamespace(id=22)
        room = SimpleNamespace(session_id=12)
        session = SimpleNamespace(id=12, host_id=user.id)
        db = SimpleNamespace(
            execute=AsyncMock(side_effect=[
                _ScalarResult(None),
                _ScalarResult(room),
            ]),
            get=AsyncMock(return_value=session),
            commit=AsyncMock(),
        )
        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username="example_bot")),
        )

        with (
            patch(
                "app.bot.services.quiz_room.registered_user",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "app.bot.services.quiz_room.AsyncSessionLocal",
                return_value=_SessionContext(db),
            ),
            patch(
                "app.bot.services.quiz_room.MultiplayerQuizService",
            ) as service_class,
            patch(
                "app.bot.services.quiz_room.publish_room",
                new_callable=AsyncMock,
            ) as publish_room,
        ):
            session_id = await create_room(
                bot,
                telegram_id=42,
                chat_id=-100123,
                message_id=555,
                quiz_id=7,
                duration=15,
            )

        self.assertEqual(session_id, session.id)
        service_class.assert_not_called()
        db.commit.assert_awaited_once()
        publish_room.assert_awaited_once_with(bot, session.id)

    async def test_host_start_reuses_service_and_schedules_session_deadline(self):
        deadline = object()
        user = SimpleNamespace(id=22)
        session = SimpleNamespace(id=12, quiz_id=4, deadline_at=deadline)
        room = SimpleNamespace(chat_id=5700644405)
        service = SimpleNamespace(start=AsyncMock(return_value=session))
        callback = SimpleNamespace(
            data="room:start:12",
            from_user=SimpleNamespace(id=5700644406),
            bot=SimpleNamespace(send_message=AsyncMock()),
            message=SimpleNamespace(chat=SimpleNamespace(type="private")),
            answer=AsyncMock(),
        )

        with (
            patch(
                "app.bot.handlers.quiz_room.registered_user",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "app.bot.handlers.quiz_room.MultiplayerQuizService",
                return_value=service,
            ),
            patch(
                "app.bot.handlers.quiz_room.AsyncSessionLocal",
                return_value=_SessionContext(SimpleNamespace(
                    execute=AsyncMock(return_value=_ScalarResult(room)),
                    get=AsyncMock(),
                )),
            ),
            patch("app.bot.handlers.quiz_room.queue_room_maintenance") as queue_room,
            patch(
                "app.bot.handlers.quiz_room.publish_room",
                new_callable=AsyncMock,
            ) as publish_room,
            patch(
                "app.bot.handlers.quiz_room.send_room_start_to_participants",
                new_callable=AsyncMock,
            ) as send_start,
        ):
            await start_room(callback)

        service.start.assert_awaited_once_with(12, user)
        queue_room.assert_called_once_with(12, eta=deadline)
        publish_room.assert_awaited_once_with(callback.bot, 12)
        send_start.assert_awaited_once_with(callback.bot, 12)
        callback.answer.assert_awaited_once_with("Test boshlandi.")

    async def test_non_host_start_returns_callback_alert_only(self):
        user = SimpleNamespace(id=33)
        service = SimpleNamespace(
            start=AsyncMock(side_effect=HTTPException(
                403,
                "Faqat xona egasi testni boshlashi mumkin.",
            ))
        )
        callback = SimpleNamespace(
            data="room:start:12",
            from_user=SimpleNamespace(id=5700644407),
            answer=AsyncMock(),
        )

        with (
            patch(
                "app.bot.handlers.quiz_room.registered_user",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "app.bot.handlers.quiz_room.MultiplayerQuizService",
                return_value=service,
            ),
            patch(
                "app.bot.handlers.quiz_room.AsyncSessionLocal",
                return_value=_SessionContext(SimpleNamespace()),
            ),
            patch("app.bot.handlers.quiz_room.queue_room_maintenance") as queue_room,
            patch(
                "app.bot.handlers.quiz_room.publish_room",
                new_callable=AsyncMock,
            ) as publish_room,
        ):
            await start_room(callback)

        callback.answer.assert_awaited_once_with(
            "Faqat xona egasi testni boshlashi mumkin.",
            show_alert=True,
        )
        queue_room.assert_not_called()
        publish_room.assert_not_awaited()

    async def test_group_host_start_edits_private_control_to_player_button(self):
        deadline = object()
        user = SimpleNamespace(id=22)
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            deadline_at=deadline,
            duration_minutes=15,
        )
        room = SimpleNamespace(chat_id=-100123)
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        service = SimpleNamespace(start=AsyncMock(return_value=session))
        control_message = SimpleNamespace(
            chat=SimpleNamespace(type="private"),
            edit_text=AsyncMock(),
        )
        callback = SimpleNamespace(
            data="room:start:12",
            from_user=SimpleNamespace(id=5700644406),
            bot=SimpleNamespace(send_message=AsyncMock()),
            message=control_message,
            answer=AsyncMock(),
        )
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
        )

        with (
            patch(
                "app.bot.handlers.quiz_room.registered_user",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "app.bot.handlers.quiz_room.MultiplayerQuizService",
                return_value=service,
            ),
            patch(
                "app.bot.handlers.quiz_room.AsyncSessionLocal",
                return_value=_SessionContext(db),
            ),
            patch("app.bot.handlers.quiz_room.queue_room_maintenance") as queue_room,
            patch(
                "app.bot.handlers.quiz_room.publish_room",
                new_callable=AsyncMock,
            ) as publish_room,
            patch(
                "app.bot.handlers.quiz_room.player_keyboard",
                return_value="player-keyboard",
            ),
            patch(
                "app.bot.handlers.quiz_room.send_room_start_to_participants",
                new_callable=AsyncMock,
            ) as send_start,
        ):
            await start_room(callback)

        service.start.assert_awaited_once_with(12, user)
        queue_room.assert_called_once_with(12, eta=deadline)
        publish_room.assert_awaited_once_with(callback.bot, 12)
        send_start.assert_not_awaited()
        control_message.edit_text.assert_awaited_once()
        edited = control_message.edit_text.await_args
        self.assertIn("🚀 <b>Test boshlandi!</b>", edited.args[0])
        self.assertEqual(edited.kwargs["reply_markup"], "player-keyboard")
        callback.bot.send_message.assert_not_awaited()

    async def test_duplicate_start_is_rejected_without_duplicate_delivery(self):
        user = SimpleNamespace(id=22)
        service = SimpleNamespace(
            start=AsyncMock(side_effect=HTTPException(
                400,
                "Xona kutish holatida emas.",
            ))
        )
        callback = SimpleNamespace(
            data="room:start:12",
            from_user=SimpleNamespace(id=5700644406),
            answer=AsyncMock(),
        )

        with (
            patch(
                "app.bot.handlers.quiz_room.registered_user",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "app.bot.handlers.quiz_room.MultiplayerQuizService",
                return_value=service,
            ),
            patch(
                "app.bot.handlers.quiz_room.AsyncSessionLocal",
                return_value=_SessionContext(SimpleNamespace()),
            ),
            patch("app.bot.handlers.quiz_room.queue_room_maintenance") as queue_room,
            patch(
                "app.bot.handlers.quiz_room.publish_room",
                new_callable=AsyncMock,
            ) as publish_room,
            patch(
                "app.bot.handlers.quiz_room.send_room_start_to_participants",
                new_callable=AsyncMock,
            ) as send_start,
        ):
            await start_room(callback)

        callback.answer.assert_awaited_once_with(
            "Xona kutish holatida emas.",
            show_alert=True,
        )
        queue_room.assert_not_called()
        publish_room.assert_not_awaited()
        send_start.assert_not_awaited()

    async def test_waiting_room_join_sends_detailed_confirmation(self):
        user = SimpleNamespace(id=22)
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            host_id=1,
            join_code="ABC123",
            status="waiting",
            duration_minutes=15,
            max_participants=20,
        )
        room = SimpleNamespace(bot_username="example_bot")
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        participants = [
            {
                "first_name": "Shehroz",
                "last_name": None,
                "nickname": "tg_host",
                "is_host": True,
            },
            {
                "first_name": "Ali",
                "last_name": None,
                "nickname": "tg_ali",
                "is_host": False,
            },
        ]
        service = SimpleNamespace(
            session_repo=SimpleNamespace(get_by_join_code=AsyncMock(return_value=session)),
            participant_repo=SimpleNamespace(
                get_participant_list=AsyncMock(return_value=participants),
            ),
            lock_session=AsyncMock(return_value=session),
            join=AsyncMock(),
        )
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
        )
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=5700644406),
            bot=SimpleNamespace(),
            answer=AsyncMock(),
        )

        with (
            patch("app.bot.services.quiz_room.registered_user", new_callable=AsyncMock, return_value=user),
            patch("app.bot.services.quiz_room.MultiplayerQuizService") as service_class,
            patch("app.bot.services.quiz_room.AsyncSessionLocal", return_value=_SessionContext(db)),
            patch("app.bot.services.quiz_room.room_keyboard", return_value="room-keyboard"),
            patch(
                "app.bot.services.quiz_room.publish_room",
                new_callable=AsyncMock,
            ) as publish_room,
        ):
            service_class.return_value = service
            service_class.participant_display_name.side_effect = (
                lambda first_name, last_name, nickname: " ".join(
                    part for part in (first_name, last_name) if part
                ) or nickname
            )
            await enter_room(message, "ABC123")

        service.join.assert_awaited_once_with(session.id, user)
        publish_room.assert_awaited_once_with(message.bot, session.id)
        sent = message.answer.await_args
        self.assertIn("👥 Ishtirokchilar: 2/20", sent.args[0])
        self.assertIn("👑 Xona egasi: Shehroz", sent.args[0])
        self.assertEqual(sent.kwargs["reply_markup"], "room-keyboard")
        self.assertEqual(sent.kwargs["parse_mode"], "HTML")

    async def test_running_room_deep_link_validates_participant_then_shows_player(self):
        user = SimpleNamespace(id=22)
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            join_code="ABC123",
            status="running",
            duration_minutes=15,
        )
        room = SimpleNamespace(bot_username="example_bot")
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        service = SimpleNamespace(
            session_repo=SimpleNamespace(get_by_join_code=AsyncMock(return_value=session)),
            lock_session=AsyncMock(return_value=session),
            participant=AsyncMock(),
            finalize_quiz_session=AsyncMock(return_value=session),
        )
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
        )
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=5700644406),
            bot=SimpleNamespace(),
            answer=AsyncMock(),
        )

        with (
            patch(
                "app.bot.services.quiz_room.registered_user",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "app.bot.services.quiz_room.MultiplayerQuizService",
                return_value=service,
            ),
            patch(
                "app.bot.services.quiz_room.AsyncSessionLocal",
                return_value=_SessionContext(db),
            ),
            patch(
                "app.bot.services.quiz_room.player_keyboard",
                return_value="player-keyboard",
            ),
            patch(
                "app.bot.services.quiz_room.publish_room",
                new_callable=AsyncMock,
            ),
        ):
            await enter_room(message, "ABC123")

        service.participant.assert_awaited_once_with(12, user.id)
        sent = message.answer.await_args
        self.assertIn("🚀 <b>Test boshlandi!</b>", sent.args[0])
        self.assertIn("📚 Matematika", sent.args[0])
        self.assertEqual(sent.kwargs["reply_markup"], "player-keyboard")

    async def test_room_start_link_is_sent_to_every_participant(self):
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            status="running",
            duration_minutes=15,
        )
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        db = SimpleNamespace(
            get=AsyncMock(side_effect=[session, quiz]),
            execute=AsyncMock(return_value=_ScalarResult([
                "5700644405",
                "5700644406",
                "5700644405",
            ])),
        )
        bot = SimpleNamespace(send_message=AsyncMock())

        with patch(
            "app.bot.services.quiz_room.player_keyboard",
            return_value="room-player-keyboard",
        ):
            await send_room_start_to_participants(
                bot,
                session.id,
                session_factory=lambda: _SessionContext(db),
            )

        self.assertEqual(bot.send_message.await_count, 2)
        self.assertEqual(
            [call.kwargs["chat_id"] for call in bot.send_message.await_args_list],
            ["5700644405", "5700644406"],
        )
        for call in bot.send_message.await_args_list:
            self.assertEqual(call.kwargs["reply_markup"], "room-player-keyboard")
            self.assertIn("🚀 <b>Test boshlandi!</b>", call.kwargs["text"])
            self.assertIn("📚 Matematika — Algebra", call.kwargs["text"])
            self.assertEqual(call.kwargs["parse_mode"], "HTML")

    async def test_room_start_delivery_continues_when_one_chat_is_unavailable(self):
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            status="running",
            duration_minutes=15,
        )
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        db = SimpleNamespace(
            get=AsyncMock(side_effect=[session, quiz]),
            execute=AsyncMock(return_value=_ScalarResult([
                "5700644405",
                "5700644406",
            ])),
        )
        bot = SimpleNamespace(
            send_message=AsyncMock(side_effect=[RuntimeError("blocked"), None]),
        )

        with (
            patch("app.bot.services.quiz_room.player_keyboard", return_value=None),
            patch("app.bot.services.quiz_room.logger.exception") as log_exception,
        ):
            await send_room_start_to_participants(
                bot,
                session.id,
                session_factory=lambda: _SessionContext(db),
            )

        self.assertEqual(bot.send_message.await_count, 2)
        log_exception.assert_called_once()

    async def test_running_group_room_message_shows_started_state(self):
        room = SimpleNamespace(
            chat_id=-1005700644405,
            message_id=20,
            bot_username="example_bot",
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            join_code="ABC123",
            status="running",
            duration_minutes=5,
            max_participants=20,
        )
        quiz = SimpleNamespace(id=4, subject="Matematika", title="Test savollari")
        participant_repo = SimpleNamespace(
            get_participant_list=AsyncMock(return_value=[{
                "first_name": "Ali",
                "last_name": "Valiyev",
                "nickname": "tg_5700644405",
            }])
        )
        service = SimpleNamespace(
            lock_session=AsyncMock(return_value=session),
            participant_repo=participant_repo,
            participant_display_name=lambda first, last, nickname: f"{first} {last}",
            quiz_repo=SimpleNamespace(quiz_question_count=AsyncMock(return_value=30)),
        )
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
            commit=AsyncMock(),
        )
        bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())

        with (
            patch("app.bot.services.quiz_room.MultiplayerQuizService", return_value=service),
            patch("app.bot.services.quiz_room.room_keyboard", return_value=None),
        ):
            await publish_room(
                bot,
                session.id,
                session_factory=lambda: _SessionContext(db),
            )

        sent_text = bot.edit_message_text.await_args.args[0]
        self.assertIn("🚀 <b>Test boshlandi!</b>", sent_text)
        self.assertIn("📚 Matematika", sent_text)
        self.assertIn("📝 Test savollari", sent_text)
        self.assertIn("⏱ 5 daqiqa", sent_text)
        self.assertIn("👥 1 ishtirokchi", sent_text)
        self.assertIn("Savollar tayyor.", sent_text)

    async def test_finished_leaderboard_replaces_room_message_once(self):
        room = SimpleNamespace(
            chat_id=-1005700644405,
            message_id=20,
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        session = SimpleNamespace(id=12, quiz_id=4, status="finished", duration_minutes=5)
        quiz = SimpleNamespace(subject="Biologiya", title="Namunaviy test")
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
            commit=AsyncMock(),
        )
        service = SimpleNamespace(
            lock_session=AsyncMock(return_value=session),
            leaderboard=AsyncMock(return_value=[{
                "display_name": "Ali Valiyev",
                "total_questions": 35,
                "correct_answers": 30,
                "spend_time": 24,
            }]),
            now=AsyncMock(return_value="delivered-now"),
        )
        bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())

        with patch("app.bot.services.quiz_room.MultiplayerQuizService", return_value=service):
            await publish_room(
                bot,
                session.id,
                session_factory=lambda: _SessionContext(db),
            )
            await publish_room(
                bot,
                session.id,
                session_factory=lambda: _SessionContext(db),
            )

        bot.send_message.assert_not_awaited()
        bot.edit_message_text.assert_awaited_once()
        self.assertEqual(bot.edit_message_text.await_args.kwargs["chat_id"], room.chat_id)
        self.assertEqual(bot.edit_message_text.await_args.kwargs["message_id"], 20)
        self.assertIsNone(bot.edit_message_text.await_args.kwargs["reply_markup"])
        self.assertEqual(room.leaderboard_delivered_at, "delivered-now")
        service.leaderboard.assert_awaited_once_with(session)
        service.now.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_failed_group_leaderboard_edit_remains_recoverable(self):
        room = SimpleNamespace(
            chat_id=-1005700644405,
            message_id=20,
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            status="finished",
            duration_minutes=5,
        )
        quiz = SimpleNamespace(subject="Biologiya", title="Namunaviy test")
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
            commit=AsyncMock(),
        )
        service = SimpleNamespace(
            lock_session=AsyncMock(return_value=session),
            leaderboard=AsyncMock(return_value=[]),
            now=AsyncMock(),
        )
        bot = SimpleNamespace(
            edit_message_text=AsyncMock(side_effect=RuntimeError("Telegram unavailable")),
        )

        with patch(
            "app.bot.services.quiz_room.MultiplayerQuizService",
            return_value=service,
        ):
            with self.assertRaisesRegex(RuntimeError, "Telegram unavailable"):
                await publish_room(
                    bot,
                    session.id,
                    session_factory=lambda: _SessionContext(db),
                )

        self.assertIsNone(room.published_revision)
        self.assertIsNone(room.leaderboard_delivered_at)
        service.now.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_message_not_modified_marks_final_delivery_complete(self):
        room = SimpleNamespace(
            chat_id=-1005700644405,
            message_id=20,
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            status="finished",
            duration_minutes=5,
        )
        quiz = SimpleNamespace(subject="Biologiya", title="Namunaviy test")
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
            commit=AsyncMock(),
        )
        service = SimpleNamespace(
            lock_session=AsyncMock(return_value=session),
            leaderboard=AsyncMock(return_value=[]),
            now=AsyncMock(return_value="delivered-now"),
        )
        bot = SimpleNamespace(
            edit_message_text=AsyncMock(side_effect=TelegramBadRequest(
                method=SimpleNamespace(),
                message="Bad Request: message is not modified",
            )),
        )

        with patch(
            "app.bot.services.quiz_room.MultiplayerQuizService",
            return_value=service,
        ):
            await publish_room(
                bot,
                session.id,
                session_factory=lambda: _SessionContext(db),
            )

        self.assertIsNotNone(room.published_revision)
        self.assertEqual(room.leaderboard_delivered_at, "delivered-now")
        db.commit.assert_awaited_once()

    async def test_finished_private_room_keeps_separate_leaderboard_delivery(self):
        room = SimpleNamespace(
            chat_id=5700644405,
            message_id=20,
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            status="finished",
            duration_minutes=5,
        )
        quiz = SimpleNamespace(subject="Biologiya", title="Namunaviy test")
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
            commit=AsyncMock(),
        )
        service = SimpleNamespace(
            lock_session=AsyncMock(return_value=session),
            leaderboard=AsyncMock(return_value=[]),
            now=AsyncMock(return_value="delivered-now"),
        )
        bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())

        with patch(
            "app.bot.services.quiz_room.MultiplayerQuizService",
            return_value=service,
        ):
            await publish_room(
                bot,
                session.id,
                session_factory=lambda: _SessionContext(db),
            )

        bot.send_message.assert_awaited_once()
        bot.edit_message_text.assert_not_awaited()
        self.assertEqual(room.leaderboard_delivered_at, "delivered-now")


class TelegramQuizRoomFormattingTests(TestCase):
    def test_host_waiting_and_private_running_templates(self):
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        session = SimpleNamespace(duration_minutes=15, max_participants=20)

        waiting = format_host_waiting_room(quiz, session, 1, 30)
        running = format_private_running_room(quiz, session)

        self.assertIn("🎯 <b>Test xonasi tayyor!</b>", waiting)
        self.assertIn("❓ 30 savol", waiting)
        self.assertIn("👥 1/20 ishtirokchi", waiting)
        self.assertIn("🚀 <b>Test boshlandi!</b>", running)
        self.assertIn("📚 Matematika", running)

    @patch(
        "app.bot.keyboards.quiz_room.quiz_webapp_url",
        return_value="https://example.com/bot/webapp/?quiz_id=4",
    )
    def test_private_player_keyboard_uses_existing_room_webapp(self, _quiz_webapp_url):
        session = SimpleNamespace(id=12, quiz_id=4)

        button = player_keyboard(session).inline_keyboard[0][0]

        self.assertEqual(button.text, "📝 Testni boshlash")
        self.assertEqual(
            button.web_app.url,
            "https://example.com/bot/webapp/?quiz_id=4&room_session=12",
        )

    def test_waiting_group_room_template(self):
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        session = SimpleNamespace(duration_minutes=15, max_participants=20)
        participants = [
            {
                "first_name": "Ali",
                "last_name": "Valiyev",
                "nickname": "tg_ali",
            },
            {
                "first_name": "Madina",
                "last_name": None,
                "nickname": "tg_madina",
            },
        ]

        text = format_waiting_group_room(quiz, session, participants, 30)

        self.assertEqual(
            text,
            "🎯 <b>Test xonasi</b>\n\n"
            "📚 Matematika\n"
            "📝 Algebra\n"
            "❓ 30 savol\n"
            "⏱ 15 daqiqa\n\n"
            "👥 2/20 ishtirokchi\n"
            "1. Ali Valiyev\n"
            "2. Madina\n"
            "🟡 Boshlanishi kutilmoqda\n\n"
            "Xona egasi testni boshlashini kuting.",
        )

    def test_waiting_group_room_limits_participant_preview(self):
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        session = SimpleNamespace(duration_minutes=15, max_participants=20)
        participants = [
            {
                "first_name": f"O'quvchi {index}",
                "last_name": None,
                "nickname": f"tg_{index}",
            }
            for index in range(1, 11)
        ]

        text = format_waiting_group_room(quiz, session, participants, 30)

        self.assertIn("8. O&#x27;quvchi 8", text)
        self.assertNotIn("9. O&#x27;quvchi 9", text)
        self.assertIn("… yana 2 ishtirokchi", text)

    def test_running_group_room_template(self):
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        session = SimpleNamespace(duration_minutes=15)

        text = format_running_group_room(quiz, session, 8, 30)

        self.assertEqual(
            text,
            "🚀 <b>Test boshlandi!</b>\n\n"
            "📚 Matematika\n"
            "📝 Algebra\n"
            "❓ 30 savol\n"
            "⏱ 15 daqiqa\n"
            "👥 8 ishtirokchi\n\n"
            "Savollar tayyor.\n"
            "Testni ishlashni boshlashingiz mumkin. 👇",
        )
        self.assertNotIn("RUNNING", text)

    def test_room_start_message_matches_multiplayer_template(self):
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        session = SimpleNamespace(duration_minutes=15)

        text = format_room_start_message(quiz, session)

        self.assertIn("🚀 <b>Test boshlandi!</b>", text)
        self.assertIn("📚 Matematika — Algebra", text)
        self.assertIn("⏱ Vaqt: 15 daqiqa", text)
        self.assertIn("Savollar tayyor. Omad tilaymiz!", text)
        self.assertIn("quyidagi tugmani bosing. 👇", text)

    def test_join_confirmation_contains_room_details_and_host_name(self):
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        session = SimpleNamespace(duration_minutes=15, max_participants=20)
        participants = [
            {
                "first_name": "Shehroz",
                "last_name": None,
                "nickname": "tg_host",
                "is_host": True,
            },
            {
                "first_name": "Ali",
                "last_name": "Valiyev",
                "nickname": "tg_ali",
                "is_host": False,
            },
            {
                "first_name": "Vali",
                "last_name": None,
                "nickname": "tg_vali",
                "is_host": False,
            },
        ]

        text = format_room_join_confirmation(quiz, session, participants)

        self.assertIn("Xonaga muvaffaqiyatli qo‘shildingiz!", text)
        self.assertIn("📘 Matematika — Algebra", text)
        self.assertIn("⏱ Test vaqti: 15 daqiqa", text)
        self.assertIn("👥 Ishtirokchilar: 3/20", text)
        self.assertIn("👑 Xona egasi: Shehroz", text)
        self.assertIn("🟡 Holat: Boshlanishi kutilmoqda", text)

    @patch(
        "app.bot.keyboards.quiz_room.quiz_webapp_url",
        return_value="https://example.com/bot/webapp/?quiz_id=4",
    )
    def test_running_room_opens_webapp_directly(self, _quiz_webapp_url):
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            join_code="ABC123",
            status="running",
        )

        keyboard = room_keyboard(session, "example_bot", is_host=False)
        open_button = keyboard.inline_keyboard[0][0]

        self.assertIsNone(open_button.url)
        self.assertEqual(
            open_button.web_app.url,
            "https://example.com/bot/webapp/?quiz_id=4&room_session=12",
        )
        self.assertEqual(open_button.text, "🚀 Testni boshlash")

    def test_group_waiting_room_has_only_join_button(self):
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            join_code="ABC123",
            status="waiting",
        )

        keyboard = room_keyboard(
            session,
            "example_bot",
            is_host=True,
            group_chat=True,
        )

        self.assertEqual(len(keyboard.inline_keyboard), 1)
        join_button = keyboard.inline_keyboard[0][0]
        self.assertEqual(join_button.text, "➕ Testga qo‘shilish")
        self.assertEqual(
            join_button.url,
            "https://t.me/example_bot?start=room_ABC123",
        )

    def test_private_waiting_room_keeps_existing_host_button_label(self):
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            join_code="ABC123",
            status="waiting",
        )

        keyboard = room_keyboard(session, "example_bot", is_host=True)

        self.assertEqual(keyboard.inline_keyboard[0][0].text, "🚀 Boshlash")

    def test_running_group_room_returns_to_private_bot(self):
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            join_code="ABC123",
            status="running",
        )

        keyboard = room_keyboard(
            session,
            "example_bot",
            is_host=True,
            group_chat=True,
        )
        start_button = keyboard.inline_keyboard[0][0]

        self.assertEqual(start_button.text, "📝 Testni ishlash")
        self.assertEqual(
            start_button.url,
            "https://t.me/example_bot?start=room_ABC123",
        )
        self.assertIsNone(start_button.web_app)

    def test_waiting_room_participant_only_sees_share_button(self):
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            join_code="ABC123",
            status="waiting",
        )

        keyboard = room_keyboard(session, "example_bot", is_host=False)

        self.assertEqual(len(keyboard.inline_keyboard), 1)
        share_button = keyboard.inline_keyboard[0][0]
        self.assertEqual(share_button.text, "👥 Do‘stlarga ulashish")
        self.assertIsNone(share_button.callback_data)

    def test_leaderboard_uses_participant_full_name(self):
        quiz = SimpleNamespace(subject="Biologiya", title="Namunaviy test")
        session = SimpleNamespace(duration_minutes=5)

        text = format_leaderboard(
            quiz,
            session,
            [
                {
                    "display_name": "Ali Valiyev",
                    "total_questions": 35,
                    "correct_answers": 30,
                    "spend_time": 24,
                }
            ],
        )

        self.assertEqual(
            text,
            "🏆 <b>Test yakunlandi!</b>\n\n"
            "📚 Biologiya\n"
            "📝 Namunaviy test\n\n"
            "⏱ 5 daqiqa\n"
            "👥 1 ishtirokchi\n"
            "❓ 35 ta savol\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🥇 <b>Ali Valiyev</b>\n"
            "✅ 30 / 35\n"
            "🎯 86%\n"
            "⏱ 00:24\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "💪 Har bir test — yangi tajriba.\n"
            "Keyingi safar yanada yaxshi natija ko‘rsatishga harakat qiling!",
        )
        self.assertNotIn("tg_", text)

    def test_group_leaderboard_uses_existing_order_and_compact_template(self):
        quiz = SimpleNamespace(subject="Biologiya", title="Namunaviy test")
        session = SimpleNamespace(duration_minutes=5)
        rows = [
            {
                "display_name": "Ali Valiyev",
                "total_questions": 35,
                "correct_answers": 30,
                "spend_time": 24,
            },
            {
                "display_name": "Madina Karimova",
                "total_questions": 35,
                "correct_answers": 28,
                "spend_time": 75,
            },
            {
                "display_name": "Sardor Aliyev",
                "total_questions": 35,
                "correct_answers": 25,
                "spend_time": 125,
            },
            {
                "display_name": "Dilshod Tursunov",
                "total_questions": 35,
                "correct_answers": 20,
                "spend_time": 185,
            },
        ]

        text = format_group_leaderboard(quiz, session, rows)

        self.assertEqual(
            text,
            "🏆 <b>Test yakunlandi!</b>\n\n"
            "📚 Biologiya\n"
            "📝 Namunaviy test\n\n"
            "⏱ 5 daqiqa\n"
            "👥 4 ishtirokchi\n"
            "❓ 35 savol\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🏅 <b>LEADERBOARD</b>\n\n"
            "🥇 <b>Ali Valiyev</b>\n"
            "✅ 30/35  •  🎯 86%  •  ⏱ 00:24\n\n"
            "🥈 <b>Madina Karimova</b>\n"
            "✅ 28/35  •  🎯 80%  •  ⏱ 01:15\n\n"
            "🥉 <b>Sardor Aliyev</b>\n"
            "✅ 25/35  •  🎯 71%  •  ⏱ 02:05\n\n"
            "4. <b>Dilshod Tursunov</b>\n"
            "✅ 20/35  •  🎯 57%  •  ⏱ 03:05\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🔥 Zo‘r bellashuv!\n"
            "Keyingi testda kim 1-o‘rinni oladi?",
        )

    def test_group_leaderboard_summarizes_future_overflow(self):
        quiz = SimpleNamespace(subject="Matematika", title="Algebra")
        session = SimpleNamespace(duration_minutes=15)
        rows = [
            {
                "display_name": f"O'quvchi {position}",
                "total_questions": 30,
                "correct_answers": 30 - position,
                "spend_time": position,
            }
            for position in range(25)
        ]

        text = format_group_leaderboard(quiz, session, rows)

        self.assertIn("20. <b>O&#x27;quvchi 19</b>", text)
        self.assertNotIn("21. <b>O&#x27;quvchi 20</b>", text)
        self.assertIn("… yana 5 ishtirokchi", text)
        self.assertLess(len(text), 4096)

    def test_group_leaderboard_stays_within_limit_after_html_escaping(self):
        quiz = SimpleNamespace(subject="&" * 80, title="<" * 180)
        session = SimpleNamespace(duration_minutes=15)
        rows = [
            {
                "display_name": "&" * 60,
                "total_questions": 30,
                "correct_answers": 20,
                "spend_time": 90,
            }
            for _ in range(20)
        ]

        text = format_group_leaderboard(quiz, session, rows)

        self.assertLessEqual(len(text), 4000)
        self.assertIn("… yana ", text)
        self.assertTrue(text.endswith("Keyingi testda kim 1-o‘rinni oladi?"))
