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
        self.assertIn("7/10", text)
        self.assertIn("8/10", text)
        self.assertIn("70%", text)
        self.assertIn("02:05", text)
