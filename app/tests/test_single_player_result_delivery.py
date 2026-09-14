from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from app.bot.services.single_player_result import (
    deliver_single_player_result,
    format_single_player_result,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class SinglePlayerResultDeliveryTests(IsolatedAsyncioTestCase):
    async def test_delivered_row_does_not_send_again(self):
        delivery = SimpleNamespace(delivered_at=object())
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(delivery)),
            commit=AsyncMock(),
        )
        bot = SimpleNamespace(send_message=AsyncMock())

        await deliver_single_player_result(
            bot,
            delivery_id=17,
            session_factory=lambda: _SessionContext(session),
        )

        bot.send_message.assert_not_awaited()
        session.commit.assert_not_awaited()


class SinglePlayerResultFormattingTests(TestCase):
    def test_formats_authoritative_result_fields(self):
        text = format_single_player_result(
            {
                "quiz_title": "Algebra <Basics>",
                "subject": "Math & Logic",
                "total_questions": 10,
                "answered_questions": 8,
                "correct_answers": 7,
                "percentage": 70.0,
                "spend_time": 125,
            }
        )

        self.assertIn("Algebra &lt;Basics&gt;", text)
        self.assertIn("Math &amp; Logic", text)
        self.assertIn("🎯 Natija: <b>7/10 · 70%</b>", text)
        self.assertIn("⚪️ Javobsiz: <b>2</b>", text)
        self.assertIn("⏱ <b>02:05</b>", text)
        # A solo attempt has no room, so none of the leaderboard lines appear.
        self.assertNotIn("Xonada:", text)
        self.assertNotIn("o‘rtacha natija", text)

    def test_topic_breakdown_reaches_the_single_player_message(self):
        text = format_single_player_result(
            {
                "quiz_title": "Matematika test savollari",
                "subject": "Matematika",
                "total_questions": 30,
                "answered_questions": 30,
                "correct_answers": 11,
                "wrong_answers": 19,
                "percentage": 36.67,
                "spend_time": 45,
                "topic_statistic": [
                    {"topic_name": "Geometriya", "total_questions": 10, "correct_answers": 3},
                    {"topic_name": "Vektorlar", "total_questions": 4, "correct_answers": 4},
                    {"topic_name": "Hisoblashlar", "total_questions": 1, "correct_answers": 0},
                ],
            }
        )

        self.assertIn("🔻 <b>Zaif mavzular</b>", text)
        self.assertIn("• Geometriya — 3/10 · 30%", text)
        self.assertIn("🟢 <b>Kuchli mavzular</b>", text)
        self.assertIn("• Vektorlar — 4/4 · 100%", text)
        self.assertIn("Eng ko‘p yo‘qotish — <b>Geometriya</b>: 10 tadan 7 tasi.", text)
        # One-question topics stay out of both lists.
        self.assertNotIn("Hisoblashlar", text)
