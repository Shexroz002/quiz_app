"""Kanal testi: ochiq sessiya, deadlinesiz, admin yakunlaguncha."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.bot.handlers.channel import (
    pick_remembered_channel,
    receive_channel,
    start_channel_flow,
)
from app.bot.handlers.menu import publish_chosen_quiz
from app.bot.keyboards.quiz_room import CHANNEL_FINISH, CHANNEL_REFRESH, channel_host_keyboard
from app.bot.services.quiz_room import (
    create_channel_room,
    enter_room,
    format_channel_closed,
    format_channel_host_control,
    format_channel_room,
    publish_room,
)
from app.bot.states import CHANNEL_TARGET_KEY, ChannelQuizState
from app.models.quiz.real_time_quiz.quiz_session import SessionType
from app.services.quiz.multiplayer import is_open_session

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
#: Hali kelmagan muddat: "vaqt tugadi" qoidasi ishga tushmasligi uchun.
LATER = datetime.now(timezone.utc) + timedelta(days=1)
CHANNEL_ID = -1001234567890


class _ScalarResult:
    def __init__(self, value, rows=()):
        self.value = value
        self.rows = list(rows)

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def open_session(**overrides):
    session = SimpleNamespace(
        id=12,
        quiz_id=4,
        host_id=7,
        join_code="ABC123",
        status="running",
        session_type=SessionType.public,
        duration_minutes=15,
        max_participants=None,
        started_at=NOW,
        deadline_at=None,
    )
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


class OpenSessionTests(TestCase):
    def test_a_started_session_without_a_deadline_is_open(self):
        self.assertTrue(is_open_session(open_session()))

    def test_a_normal_room_has_a_deadline(self):
        self.assertFalse(is_open_session(open_session(deadline_at=NOW + timedelta(minutes=15))))

    def test_a_waiting_room_is_not_open_yet(self):
        self.assertFalse(is_open_session(open_session(started_at=None, status="waiting")))


class OpenSessionNeverSelfClosesTests(IsolatedAsyncioTestCase):
    """Eng muhim qoida: birinchi yakunlagan o'quvchi testni yopib qo'ymasligi kerak."""

    async def _finalize(self, session):
        from app.services.quiz.multiplayer import MultiplayerQuizService

        service = MultiplayerQuizService.__new__(MultiplayerQuizService)
        service.lock_session = AsyncMock(return_value=session)
        service.finalize_session = AsyncMock()
        service.attempt_repo = SimpleNamespace(
            all_session_attempts_finished=AsyncMock(return_value=True),
        )
        service.session_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=session))
        await service.finalize_quiz_session(session.id)
        return service

    async def test_all_finished_does_not_close_an_open_session(self):
        service = await self._finalize(open_session())

        service.finalize_session.assert_not_awaited()

    async def test_all_finished_still_closes_a_normal_room(self):
        # Deadline hali kelmagan bo'lishi kerak, aks holda "time_expired" ishlaydi.
        service = await self._finalize(open_session(deadline_at=LATER))

        service.finalize_session.assert_awaited_once_with(12, "all_finished")


class OpenLeaderboardTests(IsolatedAsyncioTestCase):
    """Ochiq sessiyada vaqt har kimning o'ziniki, ishlamaganlar jadvalga tushmaydi."""

    async def _leaderboard(self, rows, attempts):
        from app.services.quiz.multiplayer import MultiplayerQuizService

        service = MultiplayerQuizService.__new__(MultiplayerQuizService)
        service.db = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(all=lambda: attempts))
        )
        return await service._open_session_leaderboard(open_session(), rows)

    async def test_only_players_with_a_finished_attempt_are_listed(self):
        rows = [
            {"participant_id": 1, "correct_answers": 9, "spend_time": 99999},
            {"participant_id": 2, "correct_answers": 0, "spend_time": 0},
        ]
        attempts = [(1, NOW, NOW + timedelta(minutes=6))]

        table = await self._leaderboard(rows, attempts)

        self.assertEqual([row["participant_id"] for row in table], [1])

    async def test_time_is_measured_from_the_players_own_start(self):
        rows = [{"participant_id": 1, "correct_answers": 9, "spend_time": 99999}]
        # Test uch soat oldin e'lon qilingan, o'quvchi esa 6 daqiqa ishlagan.
        attempts = [(1, NOW + timedelta(hours=3), NOW + timedelta(hours=3, minutes=6))]

        table = await self._leaderboard(rows, attempts)

        self.assertEqual(table[0]["spend_time"], 360)

    async def test_a_faster_player_with_the_same_score_ranks_higher(self):
        rows = [
            {"participant_id": 1, "correct_answers": 8, "spend_time": 0},
            {"participant_id": 2, "correct_answers": 8, "spend_time": 0},
        ]
        attempts = [
            (1, NOW, NOW + timedelta(minutes=9)),
            (2, NOW, NOW + timedelta(minutes=4)),
        ]

        table = await self._leaderboard(rows, attempts)

        self.assertEqual([row["participant_id"] for row in table], [2, 1])


class JoinGuardTests(IsolatedAsyncioTestCase):
    """Haqiqiy join yo'li: kanalda "Session already started" chiqqan joy.

    Avvalgi test ``service.join`` ni mock qilgani uchun bu qoida umuman
    ishlamagan edi, shuning uchun bu yerda real metod chaqiriladi.
    """

    async def _join(self, session):
        from app.services.quiz.quiz_session import QuizSessionService

        service = QuizSessionService.__new__(QuizSessionService)
        service.session_repo = SimpleNamespace(
            get_by_join_code=AsyncMock(return_value=session),
        )
        service.participant_repo = SimpleNamespace(
            get_by_session_user=AsyncMock(return_value=SimpleNamespace(id=3)),
            mark_ready=AsyncMock(),
        )
        service.db = SimpleNamespace(commit=AsyncMock())
        with patch("app.services.quiz.quiz_session.session_ws_manager") as ws:
            ws.broadcast = AsyncMock()
            ws.count = lambda session_id: 0
            return await service.join_quiz_session("ABC123", SimpleNamespace(id=22))

    async def test_a_running_open_session_still_accepts_players(self):
        joined = await self._join(open_session())

        self.assertEqual(joined.id, 12)

    async def test_a_waiting_room_is_untouched(self):
        joined = await self._join(open_session(status="waiting", started_at=None))

        self.assertEqual(joined.id, 12)

    async def test_a_running_normal_room_is_still_closed(self):
        with self.assertRaises(HTTPException) as caught:
            await self._join(open_session(deadline_at=LATER))

        self.assertEqual(caught.exception.detail, "Session already started")

    async def test_a_finished_channel_quiz_cannot_be_joined(self):
        with self.assertRaises(HTTPException) as caught:
            await self._join(open_session(status="finished"))

        self.assertEqual(caught.exception.detail, "Session already started")


class PlayerFinishTests(IsolatedAsyncioTestCase):
    """O'quvchi testni tugatganda kanal testi yopilib qolmasligi kerak.

    Bu ikkinchi avtomatik yopish yo'li: ``finish_quiz`` ``finalize_quiz_session``
    dan mustaqil ravishda "hamma tugatdi" qoidasini qo'llaydi.
    """

    async def _finish(self, session, *, everybody_finished=True):
        from app.services.quiz.quiz_session import QuizSessionService

        attempt = SimpleNamespace(
            id=5,
            finished=False,
            finished_at=None,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=7),
        )
        service = QuizSessionService.__new__(QuizSessionService)
        service.session_repo = SimpleNamespace(
            get_by_id_for_update=AsyncMock(return_value=session),
        )
        service.participant_repo = SimpleNamespace(
            get_by_session_user=AsyncMock(return_value=SimpleNamespace(id=3)),
        )
        service.attempt_repo = SimpleNamespace(
            get_or_create=AsyncMock(return_value=attempt),
            all_session_attempts_finished=AsyncMock(return_value=everybody_finished),
        )
        service.finalize_session = AsyncMock()
        service._build_attempt_result = AsyncMock(return_value={"score": 8})
        service.db = SimpleNamespace(flush=AsyncMock(), commit=AsyncMock())
        result = await service.finish_quiz(12, SimpleNamespace(id=22))
        return service, result

    async def test_an_open_session_stays_open_after_a_player_finishes(self):
        service, _ = await self._finish(open_session())

        service.finalize_session.assert_not_awaited()
        service.db.commit.assert_awaited_once()

    async def test_a_normal_room_still_closes_when_everybody_is_done(self):
        service, _ = await self._finish(open_session(deadline_at=LATER))

        service.finalize_session.assert_awaited_once_with(12, "all_finished")

    async def test_an_open_session_reports_the_players_own_time(self):
        _, result = await self._finish(open_session())

        self.assertAlmostEqual(result["spend_time"], 7 * 60, delta=5)


class ChannelPostTests(IsolatedAsyncioTestCase):
    """Kanal posti: ochiq holatda va yakunlangandan keyin."""

    def _db(self, session, room, quiz, host_attempts=0):
        return SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
            scalar=AsyncMock(return_value=host_attempts),
            commit=AsyncMock(),
        )

    async def _publish(self, session, room, *, rows=(), participants=(), host_attempts=0):
        quiz = SimpleNamespace(id=4, subject="Fizika", title="Kinematika asoslari")
        service = SimpleNamespace(
            lock_session=AsyncMock(return_value=session),
            leaderboard=AsyncMock(return_value=list(rows)),
            participant_repo=SimpleNamespace(
                get_participant_list=AsyncMock(return_value=list(participants)),
            ),
            quiz_repo=SimpleNamespace(quiz_question_count=AsyncMock(return_value=10)),
            now=AsyncMock(return_value=NOW),
        )
        bot = SimpleNamespace(
            edit_message_text=AsyncMock(),
            edit_message_caption=AsyncMock(),
            send_message=AsyncMock(),
        )
        db = self._db(session, room, quiz, host_attempts)
        with (
            patch("app.bot.services.quiz_room.MultiplayerQuizService", return_value=service),
            patch(
                "app.bot.services.quiz_room.create_room_analysis_deliveries",
                new_callable=AsyncMock,
                return_value=[5],
            ),
            patch("app.bot.services.quiz_room.queue_room_analysis_deliveries") as queue_analysis,
            patch("app.bot.services.quiz_room.room_keyboard", return_value="join-keyboard"),
        ):
            await publish_room(bot, session.id, session_factory=lambda: _SessionContext(db))
        return bot, queue_analysis

    async def test_open_post_invites_anyone_without_promising_a_countdown(self):
        room = SimpleNamespace(
            chat_id=CHANNEL_ID,
            message_id=55,
            bot_username="edunova_bot",
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        participants = [
            {"is_host": True, "first_name": "Shehroz", "last_name": None, "nickname": None},
            {"is_host": False, "first_name": "Ali", "last_name": None, "nickname": None},
        ]

        bot, _ = await self._publish(open_session(), room, participants=participants)

        text = bot.edit_message_caption.await_args.kwargs["caption"]
        self.assertIn("📣 <b>Yangi test</b>", text)
        self.assertIn("Istalgan vaqtda", text)
        # Testni e'lon qilgan admin ishtirokchi emas.
        self.assertIn("👥 1 ishtirokchi", text)
        self.assertEqual(bot.edit_message_caption.await_args.kwargs["reply_markup"], "join-keyboard")

    async def test_a_host_who_took_the_quiz_counts_as_a_player(self):
        # Aks holda karta "1 ishtirokchi · 2 yakunladi" deb ziddiyatli ko'rinadi.
        room = SimpleNamespace(
            chat_id=CHANNEL_ID,
            message_id=55,
            bot_username="edunova_bot",
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        participants = [
            {"is_host": True, "first_name": "Shehroz", "last_name": None, "nickname": None},
            {"is_host": False, "first_name": "Ali", "last_name": None, "nickname": None},
        ]

        bot, _ = await self._publish(
            open_session(), room, participants=participants, host_attempts=1
        )

        self.assertIn("👥 2 ishtirokchi", bot.edit_message_caption.await_args.kwargs["caption"])

    async def test_finishing_keeps_the_post_and_sends_the_table_separately(self):
        room = SimpleNamespace(
            chat_id=CHANNEL_ID,
            message_id=55,
            bot_username="edunova_bot",
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        rows = [{
            "display_name": "Ali",
            "correct_answers": 9,
            "total_questions": 10,
            "spend_time": 361,
        }]

        bot, queue_analysis = await self._publish(
            open_session(status="finished"), room, rows=rows
        )

        edited = bot.edit_message_caption.await_args.kwargs["caption"]
        self.assertIn("🔒 <b>Test yakunlandi</b>", edited)
        sent = bot.send_message.await_args.kwargs
        self.assertEqual(sent["chat_id"], CHANNEL_ID)
        self.assertIn("🏆 <b>Test yakunlandi!</b>", sent["text"])
        self.assertIn("Ali", sent["text"])
        # Har bir ishtirokchiga shaxsiy tahlil ham ketadi.
        queue_analysis.assert_called_once_with([5])


class LateJoinTests(IsolatedAsyncioTestCase):
    """Ochiq testga kech kelgan odam ham ishtirokchi bo'lib qo'shiladi."""

    async def _enter(self, session):
        user = SimpleNamespace(id=22)
        room = SimpleNamespace(bot_username="edunova_bot")
        quiz = SimpleNamespace(subject="Fizika", title="Kinematika")
        service = SimpleNamespace(
            session_repo=SimpleNamespace(get_by_join_code=AsyncMock(return_value=session)),
            lock_session=AsyncMock(return_value=session),
            join=AsyncMock(),
            participant=AsyncMock(),
            finalize_quiz_session=AsyncMock(),
            participant_repo=SimpleNamespace(get_participant_list=AsyncMock(return_value=[])),
        )
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(room)),
            get=AsyncMock(return_value=quiz),
        )
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=500),
            bot=SimpleNamespace(),
            answer=AsyncMock(),
        )
        with (
            patch("app.bot.services.quiz_room.registered_user", new_callable=AsyncMock, return_value=user),
            patch("app.bot.services.quiz_room.MultiplayerQuizService", return_value=service),
            patch("app.bot.services.quiz_room.AsyncSessionLocal", return_value=_SessionContext(db)),
            patch("app.bot.services.quiz_room.player_keyboard", return_value="play-keyboard"),
            patch("app.bot.services.quiz_room.publish_room", new_callable=AsyncMock),
        ):
            await enter_room(message, "ABC123")
        return service, message

    async def test_an_open_session_admits_a_newcomer(self):
        service, message = await self._enter(open_session())

        service.join.assert_awaited_once_with(12, SimpleNamespace(id=22))
        service.participant.assert_not_awaited()
        self.assertEqual(message.answer.await_args.kwargs["reply_markup"], "play-keyboard")

    async def test_a_normal_running_room_still_checks_membership(self):
        service, _ = await self._enter(open_session(deadline_at=LATER))

        service.participant.assert_awaited_once()
        service.join.assert_not_awaited()


class CreateChannelRoomTests(IsolatedAsyncioTestCase):
    def _bot(self, *, author_status="creator"):
        return SimpleNamespace(
            send_photo=AsyncMock(return_value=SimpleNamespace(message_id=55)),
            get_me=AsyncMock(return_value=SimpleNamespace(id=1, username="edunova_bot")),
            get_chat=AsyncMock(return_value=SimpleNamespace(type="channel")),
            get_chat_member=AsyncMock(side_effect=[
                SimpleNamespace(status="administrator", can_post_messages=True),
                SimpleNamespace(status=author_status),
            ]),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=55)),
            delete_message=AsyncMock(),
        )

    async def _create(self, *, create_error=None, author_status="creator"):
        bot = self._bot(author_status=author_status)
        session = open_session()
        service = SimpleNamespace(
            create_open_session=AsyncMock(side_effect=create_error)
            if create_error
            else AsyncMock(return_value=session),
        )
        db = SimpleNamespace(
            add=lambda row: added.append(row),
            get=AsyncMock(return_value=SimpleNamespace(subject="Fizika", title="Kinematika")),
            commit=AsyncMock(),
            execute=AsyncMock(return_value=_ScalarResult(
                SimpleNamespace(id=4, subject="Fizika", title="Kinematika")
            )),
            scalar=AsyncMock(return_value=10),
        )
        added = []
        with (
            patch("app.bot.services.quiz_room.registered_user", new_callable=AsyncMock,
                  return_value=SimpleNamespace(id=7)),
            patch("app.bot.services.quiz_room.MultiplayerQuizService", return_value=service),
            patch("app.bot.services.quiz_room.AsyncSessionLocal", return_value=_SessionContext(db)),
            patch("app.bot.services.quiz_room.publish_room", new_callable=AsyncMock) as publish,
            patch("app.bot.services.quiz_room.safe_cover", return_value=b"jpeg-bytes"),
        ):
            if create_error or author_status != "creator":
                with self.assertRaises(HTTPException):
                    await create_channel_room(bot, 500, CHANNEL_ID, 4, 15)
            else:
                await create_channel_room(bot, 500, CHANNEL_ID, 4, 15)
        return bot, added, publish, service

    async def test_the_post_is_created_first_and_owned_by_the_room(self):
        bot, added, publish, service = await self._create()

        # Kanalga avval muqova rasm ketadi, matn emas.
        self.assertEqual(bot.send_photo.await_args.kwargs["chat_id"], CHANNEL_ID)
        room = added[0]
        self.assertEqual((room.chat_id, room.message_id), (CHANNEL_ID, 55))
        publish.assert_awaited_once_with(bot, 12)
        service.create_open_session.assert_awaited_once_with(
            quiz_id=4, duration_minutes=15, user=SimpleNamespace(id=7)
        )

    async def test_the_host_gets_private_controls(self):
        bot, *_ = await self._create()

        control = bot.send_message.await_args_list[-1].kwargs
        self.assertEqual(control["chat_id"], 500)
        self.assertIn("🎛 <b>Kanal testi faol</b>", control["text"])
        buttons = control["reply_markup"].inline_keyboard
        self.assertEqual(
            [button[0].callback_data for button in buttons],
            [f"{CHANNEL_REFRESH}12", f"{CHANNEL_FINISH}12"],
        )

    async def test_a_demoted_admin_cannot_publish_any_more(self):
        # Huquq kanalni tanlagandan keyin olib qo'yilishi mumkin, shuning uchun
        # joylash paytida qaytadan tekshiriladi.
        bot, added, publish, service = await self._create(author_status="member")

        bot.send_photo.assert_not_awaited()
        bot.send_message.assert_not_awaited()
        self.assertEqual(added, [])
        publish.assert_not_awaited()
        service.create_open_session.assert_not_awaited()

    async def test_a_failed_quiz_leaves_no_orphan_post_in_the_channel(self):
        bot, _, publish, _ = await self._create(
            create_error=HTTPException(400, "Ba'zi savollarda to'g'ri javob belgilanmagan.")
        )

        bot.delete_message.assert_awaited_once_with(chat_id=CHANNEL_ID, message_id=55)
        publish.assert_not_awaited()


class PublishTargetTests(IsolatedAsyncioTestCase):
    """Vaqt tanlangach: kanalgami yoki do'stlar xonasigami."""

    async def _publish(self, data):
        state = SimpleNamespace(
            get_data=AsyncMock(return_value=data),
            update_data=AsyncMock(),
        )
        with (
            patch("app.bot.handlers.menu.create_channel_room", new_callable=AsyncMock) as channel,
            patch("app.bot.handlers.menu.create_room", new_callable=AsyncMock) as room,
        ):
            answer = await publish_chosen_quiz(
                "bot", state, telegram_id=500, chat_id=99,
                message_id=123, quiz_id=4, minutes=15,
            )
        return answer, channel, room, state

    async def test_a_picked_channel_wins(self):
        answer, channel, room, state = await self._publish({CHANNEL_TARGET_KEY: CHANNEL_ID})

        channel.assert_awaited_once_with("bot", 500, CHANNEL_ID, 4, 15)
        room.assert_not_awaited()
        self.assertEqual(answer, "Kanalga joylandi.")
        # Keyingi "Do'stlar bilan" oqimi kanalga joylab yubormasligi kerak.
        state.update_data.assert_awaited_once_with(**{CHANNEL_TARGET_KEY: None})

    async def test_without_a_channel_it_is_a_friends_room(self):
        answer, channel, room, _ = await self._publish({})

        room.assert_awaited_once_with("bot", 500, 99, 123, 4, 15)
        channel.assert_not_awaited()
        self.assertEqual(answer, "Xona yaratildi.")


class ChannelBindingTests(IsolatedAsyncioTestCase):
    """Kanal forward qilingan post orqali aniqlanadi -- kanal postlari o'qilmaydi."""

    def _message(self, *, channel=True):
        chat = SimpleNamespace(id=CHANNEL_ID, type="channel" if channel else "group", title="EduNova")
        return SimpleNamespace(
            from_user=SimpleNamespace(id=500),
            forward_from_chat=chat,
            forward_origin=None,
            answer=AsyncMock(),
            bot=SimpleNamespace(
                get_me=AsyncMock(return_value=SimpleNamespace(id=1, username="edunova_bot")),
                get_chat=AsyncMock(return_value=SimpleNamespace(type="channel")),
                get_chat_member=AsyncMock(),
            ),
        )

    def _state(self):
        return SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    async def _receive(self, message, members):
        message.bot.get_chat_member.side_effect = members
        state = self._state()
        with (
            patch("app.bot.handlers.channel.show_quiz_catalog", new_callable=AsyncMock) as catalog,
            patch(
                "app.bot.handlers.channel.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=7, is_active=True),
            ),
            patch("app.bot.handlers.channel.remember_chat", new_callable=AsyncMock) as remember,
        ):
            await receive_channel(message, state)
        self.remembered = remember
        return state, catalog

    @staticmethod
    def _member(status, **extra):
        return SimpleNamespace(status=status, **extra)

    async def _start(self, channels):
        message = SimpleNamespace(from_user=SimpleNamespace(id=500), answer=AsyncMock())
        state = self._state()
        with (
            patch(
                "app.bot.handlers.channel.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=7, is_active=True),
            ),
            patch(
                "app.bot.handlers.channel.remembered_chats",
                new_callable=AsyncMock,
                return_value=channels,
            ),
        ):
            await start_channel_flow(message, state)
        return message, state

    async def test_the_first_time_it_opens_the_chat_picker(self):
        message, state = await self._start([])

        keyboard = message.answer.await_args.kwargs["reply_markup"]
        button = keyboard.keyboard[0][0]
        self.assertEqual(button.text, "📣 Kanalni tanlash")
        self.assertTrue(button.request_chat.chat_is_channel)
        # Ro'yxatda faqat ikkala tomon ham huquqli kanallar ko'rinadi.
        self.assertTrue(button.request_chat.user_administrator_rights.can_post_messages)
        self.assertTrue(button.request_chat.bot_administrator_rights.can_post_messages)

    async def test_a_remembered_channel_is_offered_instead(self):
        message, state = await self._start([{"chat_id": CHANNEL_ID, "title": "EduNova"}])

        # Forward so'ralmaydi: ro'yxatdan tanlanadi.
        state.set_state.assert_awaited_once_with(None)
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        labels = [button[0].text for button in keyboard.inline_keyboard]
        self.assertEqual(labels, ["📣 EduNova", "➕ Boshqa kanal"])
        self.assertEqual(
            keyboard.inline_keyboard[0][0].callback_data, f"channel:pick:{CHANNEL_ID}"
        )

    async def test_a_forwarded_channel_is_remembered(self):
        message = self._message()

        await self._receive(
            message,
            [
                self._member("administrator", can_post_messages=True),
                self._member("creator"),
            ],
        )

        self.remembered.assert_awaited_once_with(7, CHANNEL_ID, "EduNova", "channel")

    async def test_a_channel_the_admin_owns_is_accepted(self):
        message = self._message()

        state, catalog = await self._receive(
            message,
            [
                self._member("administrator", can_post_messages=True),
                self._member("creator"),
            ],
        )

        state.update_data.assert_awaited_once_with(**{CHANNEL_TARGET_KEY: CHANNEL_ID})
        catalog.assert_awaited_once()

    async def test_a_bot_without_posting_rights_is_refused(self):
        message = self._message()

        state, catalog = await self._receive(
            message,
            [
                self._member("administrator", can_post_messages=False),
                self._member("creator"),
            ],
        )

        state.update_data.assert_not_awaited()
        catalog.assert_not_awaited()
        self.assertIn("post yubora olmaydi", message.answer.await_args.args[0])

    async def test_a_non_admin_cannot_publish_to_the_channel(self):
        message = self._message()

        state, catalog = await self._receive(
            message,
            [
                self._member("administrator", can_post_messages=True),
                self._member("member"),
            ],
        )

        state.update_data.assert_not_awaited()
        catalog.assert_not_awaited()
        self.assertIn("administratori", message.answer.await_args.args[0])

    async def test_a_forward_from_a_group_is_not_a_channel(self):
        message = self._message(channel=False)

        state, catalog = await self._receive(message, [])

        state.update_data.assert_not_awaited()
        catalog.assert_not_awaited()


class RememberedChannelPickTests(IsolatedAsyncioTestCase):
    """Saqlangan kanal — qisqa yo'l, ruxsat emas: huquq har safar qayta so'raladi."""

    async def _pick(self, *, author_status="creator", data=None):
        callback = SimpleNamespace(
            data=data or f"channel:pick:{CHANNEL_ID}",
            from_user=SimpleNamespace(id=500),
            message=SimpleNamespace(answer=AsyncMock()),
            answer=AsyncMock(),
            bot=SimpleNamespace(
                get_me=AsyncMock(return_value=SimpleNamespace(id=1, username="edunova_bot")),
                get_chat=AsyncMock(return_value=SimpleNamespace(type="channel")),
                get_chat_member=AsyncMock(side_effect=[
                    SimpleNamespace(status="administrator", can_post_messages=True),
                    SimpleNamespace(status=author_status),
                ]),
            ),
        )
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        with (
            patch(
                "app.bot.handlers.channel.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=7, is_active=True),
            ),
            patch("app.bot.handlers.channel.show_quiz_catalog", new_callable=AsyncMock) as catalog,
        ):
            await pick_remembered_channel(callback, state)
        return callback, state, catalog

    async def test_picking_a_channel_goes_straight_to_the_quiz_list(self):
        _, state, catalog = await self._pick()

        state.update_data.assert_awaited_once_with(**{CHANNEL_TARGET_KEY: CHANNEL_ID})
        catalog.assert_awaited_once()

    async def test_lost_admin_rights_stop_the_shortcut(self):
        callback, state, catalog = await self._pick(author_status="member")

        state.update_data.assert_not_awaited()
        catalog.assert_not_awaited()
        self.assertIn("administratori", callback.answer.await_args.args[0])

    async def test_a_broken_callback_is_rejected(self):
        callback, state, catalog = await self._pick(data="channel:pick:xyz")

        state.update_data.assert_not_awaited()
        catalog.assert_not_awaited()


class PublishRightsTests(IsolatedAsyncioTestCase):
    """Guruhda bot admin bo'lishi shart emas, a'zo bo'lsa yetarli -- kanalda esa shart."""

    async def _check(self, chat_type, bot_member, author_member):
        from app.bot.services.quiz_room import ensure_publish_rights

        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(id=1)),
            get_chat=AsyncMock(return_value=SimpleNamespace(type=chat_type)),
            get_chat_member=AsyncMock(side_effect=[bot_member, author_member]),
        )
        await ensure_publish_rights(bot, 500, CHANNEL_ID)

    async def test_a_group_only_needs_the_bot_inside_it(self):
        await self._check(
            "supergroup",
            SimpleNamespace(status="member"),
            SimpleNamespace(status="administrator"),
        )

    async def test_a_bot_kicked_from_the_group_is_refused(self):
        with self.assertRaises(HTTPException) as caught:
            await self._check(
                "supergroup",
                SimpleNamespace(status="left"),
                SimpleNamespace(status="creator"),
            )

        self.assertIn("guruhda yo'q", caught.exception.detail)

    async def test_a_plain_group_member_cannot_publish(self):
        with self.assertRaises(HTTPException) as caught:
            await self._check(
                "supergroup",
                SimpleNamespace(status="member"),
                SimpleNamespace(status="member"),
            )

        self.assertIn("guruh administratori", caught.exception.detail)

    async def test_a_channel_still_needs_an_admin_bot(self):
        with self.assertRaises(HTTPException) as caught:
            await self._check(
                "channel",
                SimpleNamespace(status="member"),
                SimpleNamespace(status="creator"),
            )

        self.assertIn("post yubora olmaydi", caught.exception.detail)


class MissingBotTests(IsolatedAsyncioTestCase):
    """Tanlagich odam admin bo'lgan hamma chatni ko'rsatadi -- bot yo'qlari ham."""

    async def test_an_unreachable_chat_raises_its_own_error(self):
        from aiogram.exceptions import TelegramBadRequest
        from app.bot.services.quiz_room import ChatAccessError, ensure_publish_rights

        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(id=1)),
            get_chat=AsyncMock(side_effect=TelegramBadRequest(
                method=SimpleNamespace(), message="chat not found")),
            get_chat_member=AsyncMock(),
        )

        with self.assertRaises(ChatAccessError):
            await ensure_publish_rights(bot, 500, CHANNEL_ID)

    async def _share_into_a_chat_without_the_bot(self, request_id):
        from aiogram.exceptions import TelegramBadRequest
        from app.bot.handlers.channel import receive_picked_chat

        message = SimpleNamespace(
            from_user=SimpleNamespace(id=500),
            chat_shared=SimpleNamespace(
                request_id=request_id, chat_id=CHANNEL_ID, title="Fizika guruhi"
            ),
            answer=AsyncMock(),
            bot=SimpleNamespace(
                get_me=AsyncMock(return_value=SimpleNamespace(id=1, username="edunova_bot")),
                get_chat=AsyncMock(side_effect=TelegramBadRequest(
                    method=SimpleNamespace(), message="chat not found")),
                get_chat_member=AsyncMock(),
            ),
        )
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        with (
            patch(
                "app.bot.handlers.channel.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=7, is_active=True),
            ),
            patch("app.bot.handlers.channel.remember_chat", new_callable=AsyncMock) as remember,
            patch("app.bot.handlers.channel.show_quiz_catalog", new_callable=AsyncMock) as catalog,
        ):
            await receive_picked_chat(message, state)
        return message, state, remember, catalog

    async def test_a_group_without_the_bot_offers_an_invite_button(self):
        from app.bot.keyboards.channel import GROUP_REQUEST_ID

        message, state, remember, catalog = await self._share_into_a_chat_without_the_bot(
            GROUP_REQUEST_ID
        )

        last = message.answer.await_args
        self.assertIn("bot yo'q", last.args[0])
        button = last.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.url, "https://t.me/edunova_bot?startgroup=true")
        # Yetib bo'lmaydigan chat eslab qolinmaydi va tanlanmaydi.
        remember.assert_not_awaited()
        catalog.assert_not_awaited()
        state.update_data.assert_not_awaited()

    async def test_a_channel_without_the_bot_asks_for_the_posting_right(self):
        from app.bot.keyboards.channel import CHANNEL_REQUEST_ID

        message, *_ = await self._share_into_a_chat_without_the_bot(CHANNEL_REQUEST_ID)

        button = message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(
            button.url,
            "https://t.me/edunova_bot?startchannel=true&admin=post_messages",
        )


class ChatPickerTests(IsolatedAsyncioTestCase):
    """Telegram'ning o'z ro'yxati: guruh uchun /challenge, kanal uchun /kanal."""

    def _message(self, *, shared=None):
        return SimpleNamespace(
            from_user=SimpleNamespace(id=500),
            chat_shared=shared,
            answer=AsyncMock(),
            bot=SimpleNamespace(
                get_me=AsyncMock(return_value=SimpleNamespace(id=1, username="edunova_bot")),
                get_chat=AsyncMock(return_value=SimpleNamespace(type="supergroup")),
                get_chat_member=AsyncMock(side_effect=[
                    SimpleNamespace(status="member"),
                    SimpleNamespace(status="administrator"),
                ]),
            ),
        )

    def _state(self):
        return SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    async def test_challenge_in_the_bot_offers_the_group_list(self):
        from app.bot.handlers.channel import start_group_flow

        message, state = self._message(), self._state()
        with (
            patch(
                "app.bot.handlers.channel.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=7, is_active=True),
            ),
            # Hali bironta guruh eslab qolinmagan: tanlagich ochilishi kerak.
            patch(
                "app.bot.handlers.channel.remembered_chats",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await start_group_flow(message, state)

        button = message.answer.await_args.kwargs["reply_markup"].keyboard[0][0]
        self.assertEqual(button.text, "👥 Guruhni tanlash")
        self.assertFalse(button.request_chat.chat_is_channel)
        # Siz admin bo'lgan guruhlar; botga na adminlik, na mijoz keshiga tayanish.
        self.assertTrue(button.request_chat.user_administrator_rights.can_manage_chat)
        self.assertIsNone(button.request_chat.bot_administrator_rights)
        self.assertIsNone(button.request_chat.bot_is_member)

    def test_no_rights_set_is_empty(self):
        """Telegram bo'sh huquqlar to'plamini rad etadi: ADMIN_RIGHTS_EMPTY."""
        from app.bot.keyboards.channel import chat_picker_keyboard

        for is_channel in (True, False):
            with self.subTest(is_channel=is_channel):
                request = chat_picker_keyboard(is_channel=is_channel).keyboard[0][0].request_chat
                for rights in (request.user_administrator_rights, request.bot_administrator_rights):
                    if rights is not None:
                        self.assertTrue(any(rights.model_dump().values()))

    async def _share(self, request_id, *, title="11-sinf"):
        from app.bot.handlers.channel import receive_picked_chat

        shared = SimpleNamespace(request_id=request_id, chat_id=CHANNEL_ID, title=title)
        message, state = self._message(shared=shared), self._state()
        with (
            patch(
                "app.bot.handlers.channel.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=7, is_active=True),
            ),
            patch("app.bot.handlers.channel.remember_chat", new_callable=AsyncMock) as remember,
            patch("app.bot.handlers.channel.show_quiz_catalog", new_callable=AsyncMock) as catalog,
        ):
            await receive_picked_chat(message, state)
        return message, state, remember, catalog

    async def test_a_picked_group_goes_straight_to_the_quiz_list(self):
        from app.bot.keyboards.channel import GROUP_REQUEST_ID

        message, state, remember, catalog = await self._share(GROUP_REQUEST_ID)

        state.update_data.assert_awaited_once_with(**{CHANNEL_TARGET_KEY: CHANNEL_ID})
        catalog.assert_awaited_once()
        # Guruh ham eslab qolinadi: keyingi safar ro'yxatdan tanlanadi.
        remember.assert_awaited_once_with(7, CHANNEL_ID, "11-sinf", "group")

    async def test_a_picked_channel_is_remembered(self):
        from app.bot.keyboards.channel import CHANNEL_REQUEST_ID

        _, _, remember, catalog = await self._share(CHANNEL_REQUEST_ID, title="EduNova")

        remember.assert_awaited_once_with(7, CHANNEL_ID, "EduNova", "channel")
        catalog.assert_awaited_once()

    async def test_an_unknown_request_id_is_ignored(self):
        _, state, _, catalog = await self._share(99)

        state.update_data.assert_not_awaited()
        catalog.assert_not_awaited()


class CoverTests(TestCase):
    """Muqova — testdan chiziladi, hech qanday tayyor rasm ishlatilmaydi."""

    def test_the_cover_is_a_jpeg_sized_for_a_feed(self):
        from PIL import Image
        from io import BytesIO
        from app.bot.services.covers import render_cover

        data = render_cover("Fizika", "Kinematika asoslari", 10, 15, seed=3)

        image = Image.open(BytesIO(data))
        self.assertEqual((image.width, image.height), (1280, 720))
        self.assertEqual(image.format, "JPEG")

    def test_the_same_quiz_always_draws_the_same_picture(self):
        from app.bot.services.covers import render_cover

        first = render_cover("Fizika", "Kinematika", 10, 15, seed=12)
        second = render_cover("Fizika", "Kinematika", 10, 15, seed=12)

        self.assertEqual(first, second)

    def test_two_quizzes_in_one_subject_look_different(self):
        from app.bot.services.covers import render_cover

        self.assertNotEqual(
            render_cover("Fizika", "Kinematika", 10, 15, seed=1),
            render_cover("Fizika", "Optika", 10, 15, seed=2),
        )

    def test_every_platform_subject_has_its_own_colour(self):
        from app.services.ai.subjects import ALLOWED_SUBJECTS
        from app.bot.services.covers import FALLBACK_THEME, theme_for

        for subject in ALLOWED_SUBJECTS:
            with self.subTest(subject=subject):
                self.assertNotEqual(theme_for(subject), FALLBACK_THEME)

    def test_physics_gets_its_own_drawn_scene(self):
        """Fizika glif-fonli emas, alohida chizilgan muqovaga ega."""
        from app.bot.services.covers import render_cover

        drawn = render_cover("Fizika", "Kinematika", 10, 15, seed=5)
        other = render_cover("Kimyo", "Kinematika", 10, 15, seed=5)

        self.assertNotEqual(drawn, other)

    def test_topics_change_the_physics_cover(self):
        from app.bot.services.covers import render_cover

        without = render_cover("Fizika", "Kinematika", 10, 15, seed=5)
        with_topics = render_cover(
            "Fizika", "Kinematika", 10, 15, seed=5, topics=["Mexanika", "Optika"]
        )

        self.assertNotEqual(without, with_topics)

    def test_an_unknown_subject_still_gets_a_cover(self):
        from app.bot.services.covers import FALLBACK_THEME, render_cover, theme_for

        self.assertEqual(theme_for("Chizmachilik"), FALLBACK_THEME)
        self.assertTrue(render_cover("Chizmachilik", "Test", 5, None, seed=1))

    def test_a_broken_cover_never_blocks_publishing(self):
        from app.bot.services import covers

        with patch.object(covers, "render_cover", side_effect=OSError("shrift yo'q")):
            self.assertIsNone(covers.safe_cover("Fizika", "Test", 10, 15))


class ChannelTemplateTests(TestCase):
    QUIZ = SimpleNamespace(subject="Fizika", title="Kinematika asoslari")

    def test_the_open_post_never_shows_a_deadline(self):
        text = format_channel_room(self.QUIZ, open_session(), 24, 10)

        self.assertIn("❓ 10 savol · ⏱ ~15 daqiqa", text)
        self.assertIn("👥 24 ishtirokchi", text)

    def test_the_closed_post_points_at_the_results(self):
        text = format_channel_closed(self.QUIZ, open_session(status="finished"), 24)

        self.assertIn("🔒 <b>Test yakunlandi</b>", text)
        self.assertIn("Natijalar quyidagi xabarda", text)

    def test_the_host_card_counts_players_and_finishers(self):
        text = format_channel_host_control(self.QUIZ, open_session(), 24, 17)

        self.assertIn("👥 24 ishtirokchi · ✅ 17 yakunladi", text)

    def test_the_host_keyboard_carries_the_session(self):
        keyboard = channel_host_keyboard(12)

        self.assertEqual(
            [row[0].callback_data for row in keyboard.inline_keyboard],
            [f"{CHANNEL_REFRESH}12", f"{CHANNEL_FINISH}12"],
        )
