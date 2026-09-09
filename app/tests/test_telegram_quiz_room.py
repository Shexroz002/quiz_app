from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.bot.keyboards.quiz_room import room_keyboard
from app.bot.services.quiz_room import (
    format_leaderboard,
    format_room_join_confirmation,
    format_room_start_message,
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
            patch("app.bot.services.quiz_room.publish_room", new_callable=AsyncMock),
        ):
            service_class.return_value = service
            service_class.participant_display_name.side_effect = (
                lambda first_name, last_name, nickname: " ".join(
                    part for part in (first_name, last_name) if part
                ) or nickname
            )
            await enter_room(message, "ABC123")

        service.join.assert_awaited_once_with(session.id, user)
        sent = message.answer.await_args
        self.assertIn("👥 Ishtirokchilar: 2/20", sent.args[0])
        self.assertIn("👑 Xona egasi: Shehroz", sent.args[0])
        self.assertEqual(sent.kwargs["reply_markup"], "room-keyboard")
        self.assertEqual(sent.kwargs["parse_mode"], "HTML")

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

    async def test_running_room_message_uses_participant_full_name(self):
        room = SimpleNamespace(
            chat_id=5700644405,
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
            patch(
                "app.bot.services.quiz_room.room_webapp_url",
                return_value="https://example.com/bot/webapp/?quiz_id=4&room_session=12",
            ),
        ):
            await publish_room(
                bot,
                session.id,
                session_factory=lambda: _SessionContext(db),
            )

        sent_text = bot.edit_message_text.await_args.args[0]
        self.assertIn("Ali Valiyev", sent_text)
        self.assertNotIn("tg_5700644405", sent_text)

    async def test_finished_leaderboard_is_sent_as_new_message(self):
        room = SimpleNamespace(chat_id=5700644405, leaderboard_delivered_at=None)
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

        bot.send_message.assert_awaited_once()
        bot.edit_message_text.assert_not_awaited()
        self.assertEqual(room.leaderboard_delivered_at, "delivered-now")
        db.commit.assert_awaited_once()


class TelegramQuizRoomFormattingTests(TestCase):
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

    def test_waiting_room_has_only_start_and_share_buttons(self):
        session = SimpleNamespace(
            id=12,
            quiz_id=4,
            join_code="ABC123",
            status="waiting",
        )

        keyboard = room_keyboard(session, "example_bot", is_host=True)

        self.assertEqual(len(keyboard.inline_keyboard), 2)
        start_button = keyboard.inline_keyboard[0][0]
        share_button = keyboard.inline_keyboard[1][0]
        self.assertEqual(start_button.text, "🚀 Boshlash")
        self.assertEqual(start_button.callback_data, "room:start:12")
        self.assertEqual(share_button.text, "👥 Do‘stlarga ulashish")
        self.assertIn("https%3A%2F%2Ft.me%2Fexample_bot%3Fstart%3Droom_ABC123", share_button.url)
        self.assertIn("Test+xonasiga+qo%E2%80%98shiling%21", share_button.url)

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
