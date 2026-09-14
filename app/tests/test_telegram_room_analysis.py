from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.bot.services.analysis_message import (
    format_analysis_message,
    select_topic_highlights,
)
from app.bot.services.room_analysis import (
    create_room_analysis_deliveries,
    deliver_room_analysis,
)


def topic(name, total, correct):
    return {"topic_name": name, "total_questions": total, "correct_answers": correct}


TOPICS = [
    topic("Geometriya", 10, 5),
    topic("Trigonometriya", 3, 1),
    topic("Tengsizliklar", 3, 2),
    topic("Vektorlar", 4, 3),
    topic("Funksiyalar", 2, 2),
    topic("Sonlar va amallar", 2, 2),
    topic("Hisoblashlar", 1, 0),
    topic("Stereometriya", 1, 1),
]

RESULT = {
    "quiz_title": "Algebra va geometriya · 1-KUN",
    "subject": "Matematika",
    "total_questions": 30,
    "answered_questions": 27,
    "correct_answers": 18,
    "wrong_answers": 9,
    "percentage": 60.0,
    "spend_time": 1455,
    "topic_statistic": TOPICS,
}


def player(user_id, name, score, total=30):
    return {
        "user_id": user_id,
        "display_name": name,
        "correct_answers": score,
        "total_questions": total,
    }


LEADERBOARD = [
    player(1, "Aziz Nabiyev", 26),
    player(2, "Malika Tosheva", 22),
    player(7, "Shohruh Qodirov", 18),
    player(4, "Dilnoza Rasulova", 15),
]


class TopicHighlightTests(TestCase):
    def test_single_question_topics_never_reach_the_lists(self):
        weak, strong = select_topic_highlights(TOPICS)

        names = [row["topic_name"] for row in weak + strong]
        self.assertNotIn("Hisoblashlar", names)
        self.assertNotIn("Stereometriya", names)

    def test_weak_topics_are_the_lowest_percentages_in_order(self):
        weak, _ = select_topic_highlights(TOPICS)

        self.assertEqual(
            [(row["topic_name"], row["percent"]) for row in weak],
            [("Trigonometriya", 33), ("Geometriya", 50), ("Tengsizliklar", 67)],
        )

    def test_strong_topics_are_fully_correct_only(self):
        _, strong = select_topic_highlights(TOPICS)

        self.assertTrue(all(row["percent"] == 100 for row in strong))
        self.assertLessEqual(len(strong), 2)

    def test_empty_statistic_is_tolerated(self):
        self.assertEqual(select_topic_highlights(None), ([], []))


class RoomAnalysisMessageTests(TestCase):
    def test_message_carries_rank_result_and_topics(self):
        text = format_analysis_message(RESULT, LEADERBOARD, user_id=7)

        self.assertIn("📊 <b>Test tahlili tayyor</b>", text)
        self.assertIn("📚 Matematika", text)
        self.assertIn("👥 Xonada: <b>3-o‘rin</b> / 4 ta", text)
        self.assertIn("🎯 Natija: <b>18/30 · 60%</b>", text)
        self.assertIn("⚪️ Javobsiz: <b>3</b>", text)
        self.assertIn("⏱ <b>24:15</b>", text)
        self.assertIn("• Trigonometriya — 1/3 · 33%", text)
        self.assertIn("🟢 <b>Kuchli mavzular</b>", text)

    def test_reader_is_marked_and_others_are_named(self):
        text = format_analysis_message(RESULT, LEADERBOARD, user_id=7)

        self.assertIn("🥇 Aziz Nabiyev — 26/30", text)
        self.assertIn("🥉 <b>Siz</b> — 18/30", text)
        self.assertNotIn("Shohruh Qodirov", text)

    def test_reader_below_the_top_three_is_still_listed(self):
        text = format_analysis_message(RESULT, LEADERBOARD, user_id=4)

        self.assertIn("🥇 Aziz Nabiyev — 26/30", text)
        self.assertIn("4. <b>Siz</b> — 15/30", text)
        self.assertIn("👥 Xonada: <b>4-o‘rin</b> / 4 ta", text)

    def test_biggest_loss_counts_wrong_and_unanswered_together(self):
        text = format_analysis_message(RESULT, LEADERBOARD, user_id=7)

        # Geometriya lost 5 of 10; the message must not call them all "xato",
        # because topic statistics cannot separate wrong from unanswered.
        self.assertIn("Eng ko‘p yo‘qotish — <b>Geometriya</b>: 10 tadan 5 tasi.", text)

    def test_room_average_uses_participants_who_have_an_attempt(self):
        leaderboard = LEADERBOARD + [
            {"user_id": 9, "display_name": "Kelmagan", "correct_answers": 0, "total_questions": None}
        ]

        text = format_analysis_message(RESULT, leaderboard, user_id=7)

        # (26 + 22 + 18 + 15) / 4 = 20.25 -> 20, the absent player excluded.
        self.assertIn("Xonadagi o‘rtacha natija — 20/30.", text)

    def test_player_names_are_escaped(self):
        leaderboard = [player(7, "<b>Hacker</b>", 18)]

        text = format_analysis_message(RESULT, leaderboard, user_id=1)

        self.assertIn("&lt;b&gt;Hacker&lt;/b&gt;", text)

    def test_missing_rank_drops_the_room_lines_without_failing(self):
        text = format_analysis_message(RESULT, [], user_id=7)

        self.assertNotIn("Xonada:", text)
        self.assertNotIn("o‘rtacha natija", text)
        self.assertIn("🎯 Natija: <b>18/30 · 60%</b>", text)


class DeliveryOutboxTests(IsolatedAsyncioTestCase):
    def _db(self, participants, existing):
        results = [
            SimpleNamespace(mappings=lambda rows=participants: SimpleNamespace(all=lambda: rows)),
            SimpleNamespace(scalars=lambda rows=existing: SimpleNamespace(all=lambda: rows)),
        ]
        added = []

        async def execute(_stmt):
            return results.pop(0)

        async def flush():
            for index, delivery in enumerate(added, 1):
                delivery.id = index

        return SimpleNamespace(execute=execute, add=added.append, flush=flush), added

    async def test_one_row_per_finished_participant_with_a_telegram_id(self):
        db, added = self._db(
            [
                {"attempt_id": 11, "user_id": 1, "telegram_id": "500"},
                {"attempt_id": 12, "user_id": 2, "telegram_id": "600"},
                {"attempt_id": 13, "user_id": 3, "telegram_id": None},
            ],
            existing=[],
        )

        ids = await create_room_analysis_deliveries(db, session_id=42)

        self.assertEqual(ids, [1, 2])
        self.assertEqual([delivery.attempt_id for delivery in added], [11, 12])
        self.assertEqual([delivery.chat_id for delivery in added], [500, 600])

    async def test_already_queued_attempts_are_not_duplicated(self):
        db, added = self._db(
            [
                {"attempt_id": 11, "user_id": 1, "telegram_id": "500"},
                {"attempt_id": 12, "user_id": 2, "telegram_id": "600"},
            ],
            existing=[11],
        )

        ids = await create_room_analysis_deliveries(db, session_id=42)

        self.assertEqual(ids, [1])
        self.assertEqual([delivery.attempt_id for delivery in added], [12])

    async def test_nothing_to_send_returns_no_ids(self):
        db, added = self._db([], existing=[])

        self.assertEqual(await create_room_analysis_deliveries(db, session_id=42), [])
        self.assertEqual(added, [])


class DeliverRoomAnalysisTests(IsolatedAsyncioTestCase):
    def _session_factory(self, delivery):
        db = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(scalar_one_or_none=lambda: delivery)
            ),
            get=AsyncMock(return_value=SimpleNamespace(id=42)),
            commit=AsyncMock(),
        )

        class Factory:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *_):
                return False

        return (lambda: Factory()), db

    async def test_sends_once_and_marks_delivered(self):
        delivery = SimpleNamespace(
            id=1, session_id=42, user_id=7, chat_id=500, delivered_at=None
        )
        factory, db = self._session_factory(delivery)
        bot = SimpleNamespace(send_message=AsyncMock())

        with patch("app.bot.services.room_analysis.MultiplayerQuizService") as service:
            service.return_value.get_finished_attempt_result = AsyncMock(return_value=RESULT)
            service.return_value.leaderboard = AsyncMock(return_value=LEADERBOARD)
            await deliver_room_analysis(bot, 1, session_factory=factory)

        bot.send_message.assert_awaited_once()
        self.assertEqual(bot.send_message.await_args.kwargs["chat_id"], 500)
        self.assertIn("Xonada:", bot.send_message.await_args.kwargs["text"])
        self.assertIsNotNone(delivery.delivered_at)
        db.commit.assert_awaited_once()

    async def test_already_delivered_row_is_skipped(self):
        delivery = SimpleNamespace(
            id=1, session_id=42, user_id=7, chat_id=500, delivered_at="done"
        )
        factory, db = self._session_factory(delivery)
        bot = SimpleNamespace(send_message=AsyncMock())

        await deliver_room_analysis(bot, 1, session_factory=factory)

        bot.send_message.assert_not_awaited()
        db.commit.assert_not_awaited()


class ErrorAnalysisScopeTests(IsolatedAsyncioTestCase):
    """The query used to ignore its user argument and always return the session's
    first participant — invisible with one player, wrong for every room member."""

    async def _compiled_sql(self, user_id: int) -> str:
        from app.repositories.quiz.quiz_session_repo import QuizSessionRepository

        captured = {}

        async def execute(stmt):
            captured["stmt"] = stmt
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))

        repo = QuizSessionRepository(SimpleNamespace(execute=execute))
        await repo.get_session_questions_with_answers(42, user_id)
        return str(captured["stmt"].compile(compile_kwargs={"literal_binds": True}))

    async def test_participant_lookup_is_scoped_to_the_requesting_user(self):
        sql = await self._compiled_sql(user_id=7)

        self.assertIn("session_participants.user_id = 7", sql)

    async def test_a_different_user_produces_a_different_scope(self):
        self.assertNotEqual(
            await self._compiled_sql(user_id=7),
            await self._compiled_sql(user_id=8),
        )


class PublishRoomHookTests(IsolatedAsyncioTestCase):
    """publish_room must queue the analysis only after the outbox rows commit."""

    def _fixture(self, chat_id):
        room = SimpleNamespace(
            chat_id=chat_id,
            message_id=20,
            published_revision=None,
            leaderboard_delivered_at=None,
        )
        session = SimpleNamespace(id=12, quiz_id=4, status="finished", duration_minutes=5)
        calls = []
        db = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(
                    scalar_one=lambda: room, scalar_one_or_none=lambda: room
                )
            ),
            get=AsyncMock(return_value=SimpleNamespace(subject="Matematika", title="Test")),
            commit=AsyncMock(side_effect=lambda: calls.append("commit")),
        )
        service = SimpleNamespace(
            lock_session=AsyncMock(return_value=session),
            leaderboard=AsyncMock(return_value=[{
                "display_name": "Ali Valiyev",
                "total_questions": 30,
                "correct_answers": 25,
                "spend_time": 24,
            }]),
            now=AsyncMock(return_value="delivered-now"),
        )
        return room, session, db, service, calls

    async def _publish(self, chat_id):
        from app.bot.services.quiz_room import publish_room

        room, session, db, service, calls = self._fixture(chat_id)
        bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
        # queue_room_analysis_deliveries is sync: an AsyncMock here would only
        # return an un-awaited coroutine and record nothing.
        def queue(ids):
            calls.append(("queue", ids))

        with (
            patch("app.bot.services.quiz_room.MultiplayerQuizService", return_value=service),
            patch(
                "app.bot.services.quiz_room.create_room_analysis_deliveries",
                AsyncMock(return_value=[5, 6]),
            ),
            patch("app.bot.services.quiz_room.queue_room_analysis_deliveries", queue),
        ):
            await publish_room(bot, session.id, session_factory=lambda: _SessionContext(db))
        return calls

    async def test_group_room_queues_analysis_after_commit(self):
        calls = await self._publish(chat_id=-1005700644405)

        self.assertEqual(calls, ["commit", ("queue", [5, 6])])

    async def test_private_room_queues_analysis_after_commit(self):
        calls = await self._publish(chat_id=5700644405)

        self.assertEqual(calls, ["commit", ("queue", [5, 6])])


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_):
        return False


class UndeliverableChatTests(IsolatedAsyncioTestCase):
    """A blocked or never-opened chat can never succeed, so the row must not stay
    pending — recover_rooms would re-queue it every minute forever."""

    async def _deliver(self, error):
        from aiogram.methods import SendMessage

        delivery = SimpleNamespace(
            id=1, session_id=42, user_id=7, chat_id=500, delivered_at=None
        )
        db = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(scalar_one_or_none=lambda: delivery)
            ),
            get=AsyncMock(return_value=SimpleNamespace(id=42)),
            commit=AsyncMock(),
        )

        class Factory:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *_):
                return False

        bot = SimpleNamespace(
            send_message=AsyncMock(
                side_effect=error(method=SendMessage(chat_id=500, text="x"), message="blocked")
            )
        )

        with patch("app.bot.services.room_analysis.MultiplayerQuizService") as service:
            service.return_value.get_finished_attempt_result = AsyncMock(return_value=RESULT)
            service.return_value.leaderboard = AsyncMock(return_value=LEADERBOARD)
            await deliver_room_analysis(bot, 1, session_factory=lambda: Factory())
        return delivery, db

    async def test_blocked_bot_closes_the_row(self):
        from aiogram.exceptions import TelegramForbiddenError

        delivery, db = await self._deliver(TelegramForbiddenError)

        self.assertIsNotNone(delivery.delivered_at)
        db.commit.assert_awaited_once()

    async def test_unknown_chat_closes_the_row(self):
        from aiogram.exceptions import TelegramNotFound

        delivery, db = await self._deliver(TelegramNotFound)

        self.assertIsNotNone(delivery.delivered_at)
        db.commit.assert_awaited_once()
