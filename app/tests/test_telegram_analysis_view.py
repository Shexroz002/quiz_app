from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.bot.keyboards.inline import analysis_webapp_keyboard, analysis_webapp_url
from app.bot.services.analysis_message import analysis_keyboard
from app.bot.services.analysis_view import (
    _difficulty_breakdown,
    _topic_breakdown,
    build_attempt_analysis,
)


def question(qid, difficulty, *, selected="A", is_correct=True, topic="Geometriya"):
    return {
        "id": qid,
        "question_text": f"Savol {qid}",
        "table_markdown": None,
        "topic": topic,
        "difficulty": difficulty,
        "images": None,
        "options": [{"label": "A", "text": "bir", "is_correct": True}],
        "user_select_option": selected,
        "user_select_option_is_correct": is_correct,
    }


class DifficultyBreakdownTests(TestCase):
    def test_levels_are_ordered_easy_to_hard(self):
        rows = _difficulty_breakdown([
            question(1, "qiyin", is_correct=False),
            question(2, "oson"),
            question(3, "o‘rta"),
        ])

        self.assertEqual([row["level"] for row in rows], ["oson", "o‘rta", "qiyin"])

    def test_both_apostrophe_spellings_are_one_bucket(self):
        rows = _difficulty_breakdown([
            question(1, "o'rta"),
            question(2, "o‘rta", is_correct=False),
        ])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total"], 2)
        self.assertEqual(rows[0]["correct"], 1)
        self.assertEqual(rows[0]["percent"], 50)

    def test_unanswered_questions_count_as_not_correct(self):
        rows = _difficulty_breakdown([
            question(1, "oson", selected=None, is_correct=None),
            question(2, "oson"),
        ])

        self.assertEqual(rows[0]["correct"], 1)
        self.assertEqual(rows[0]["total"], 2)

    def test_unknown_level_keeps_its_label_and_goes_last(self):
        rows = _difficulty_breakdown([question(1, None), question(2, "oson")])

        self.assertEqual([row["level"] for row in rows], ["oson", "Belgilanmagan"])


class TopicBreakdownTests(TestCase):
    def test_weakest_topics_come_first(self):
        rows = _topic_breakdown([
            {"topic_name": "Vektorlar", "total_questions": 4, "correct_answers": 4},
            {"topic_name": "Geometriya", "total_questions": 10, "correct_answers": 3},
            {"topic_name": "Tengsizliklar", "total_questions": 3, "correct_answers": 2},
        ])

        self.assertEqual(
            [(row["topic"], row["percent"]) for row in rows],
            [("Geometriya", 30), ("Tengsizliklar", 67), ("Vektorlar", 100)],
        )

    def test_topics_without_questions_are_dropped(self):
        rows = _topic_breakdown([{"topic_name": "Bo‘sh", "total_questions": 0, "correct_answers": 0}])

        self.assertEqual(rows, [])


class BuildAnalysisTests(IsolatedAsyncioTestCase):
    RESULT = {
        "quiz_title": "Matematika test savollari",
        "subject": "Matematika",
        "total_questions": 3,
        "answered_questions": 2,
        "correct_answers": 1,
        "wrong_answers": 1,
        "percentage": 33.33,
        "spend_time": 45,
        "topic_statistic": [
            {"topic_name": "Geometriya", "total_questions": 3, "correct_answers": 1},
        ],
    }
    QUESTIONS = [
        question(1, "oson"),
        question(2, "qiyin", is_correct=False),
        question(3, "qiyin", selected=None, is_correct=None),
    ]

    async def _build(self, session):
        with patch("app.bot.services.analysis_view.MultiplayerQuizService") as service:
            service.return_value.get_finished_attempt_result = AsyncMock(return_value=self.RESULT)
            service.return_value.single_player_error_analysis = AsyncMock(return_value=self.QUESTIONS)
            service.return_value.session_repo.player_session = AsyncMock(return_value=session)
            service.return_value.leaderboard = AsyncMock(return_value=[
                {"user_id": 1, "display_name": "Aziz", "correct_answers": 3, "total_questions": 3},
                {"user_id": 7, "display_name": "Shohruh", "correct_answers": 1, "total_questions": 3},
            ])
            return await build_attempt_analysis(SimpleNamespace(), 42, 7)

    async def test_single_player_payload_has_no_room_block(self):
        from app.models.quiz.real_time_quiz.quiz_session import SessionType

        payload = await self._build(SimpleNamespace(session_type=SessionType.individual))

        self.assertIsNone(payload["room"])
        self.assertEqual(payload["unanswered_questions"], 1)
        self.assertEqual([row["level"] for row in payload["difficulty"]], ["oson", "qiyin"])
        self.assertEqual(len(payload["questions"]), 3)

    async def test_question_rows_expose_answered_and_correct_state(self):
        from app.models.quiz.real_time_quiz.quiz_session import SessionType

        payload = await self._build(SimpleNamespace(session_type=SessionType.individual))
        rows = {row["id"]: row for row in payload["questions"]}

        self.assertTrue(rows[1]["answered"] and rows[1]["is_correct"])
        self.assertTrue(rows[2]["answered"] and not rows[2]["is_correct"])
        self.assertFalse(rows[3]["answered"])
        self.assertIsNone(rows[3]["selected_option"])

    async def test_room_payload_carries_rank_average_and_top(self):
        from app.models.quiz.real_time_quiz.quiz_session import SessionType

        payload = await self._build(SimpleNamespace(session_type=SessionType.public))

        self.assertEqual(payload["room"]["rank"], 2)
        self.assertEqual(payload["room"]["participants"], 2)
        self.assertEqual(payload["room"]["average_correct"], 2)
        self.assertTrue(payload["room"]["top"][1]["is_me"])
        self.assertFalse(payload["room"]["top"][0]["is_me"])

    async def test_missing_session_is_treated_as_single_player(self):
        payload = await self._build(None)

        self.assertIsNone(payload["room"])


class AnalysisButtonTests(TestCase):
    def test_button_opens_the_analysis_mode_for_the_session(self):
        with patch(
            "app.bot.keyboards.inline.settings.TELEGRAM_WEBAPP_URL",
            "https://quiz.example/bot/webapp/",
        ):
            self.assertEqual(
                analysis_webapp_url(83),
                "https://quiz.example/bot/webapp/?session_id=83&mode=analysis",
            )
            keyboard = analysis_webapp_keyboard(83)

        self.assertEqual(keyboard.inline_keyboard[0][0].text, "📈 Batafsil tahlil")
        self.assertEqual(
            keyboard.inline_keyboard[0][0].web_app.url,
            "https://quiz.example/bot/webapp/?session_id=83&mode=analysis",
        )

    def test_message_still_sends_without_an_https_web_app_url(self):
        with patch(
            "app.bot.services.analysis_message.analysis_webapp_keyboard",
            side_effect=ValueError("HTTPS Web App URL is not available"),
        ):
            self.assertIsNone(analysis_keyboard(83))
