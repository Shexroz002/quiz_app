from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.bot.handlers.quiz import review_generated_quiz
from app.bot.handlers.webapp import QuizReviewResponse, quiz_review


def option(option_id: int, label: str, *, is_correct: bool = False):
    return SimpleNamespace(id=option_id, label=label, text=f"Variant {label}", is_correct=is_correct)


def question(question_id: int, *, correct_label: str | None = "B"):
    return SimpleNamespace(
        id=question_id,
        subject="Matematika",
        question_text=f"Savol {question_id}",
        table_markdown=None,
        difficulty="easy",
        topic="Algebra",
        images=[],
        options=[
            option(question_id * 10 + index, label, is_correct=label == correct_label)
            for index, label in enumerate("ABCD", start=1)
        ],
    )


class QuizReviewEndpointTests(IsolatedAsyncioTestCase):
    async def test_review_returns_owner_questions_with_correct_flags(self):
        quiz = SimpleNamespace(id=7, title="Algebra asoslari", subject="Matematika")
        questions = [question(1), question(2, correct_label=None)]

        with patch("app.bot.handlers.webapp.QuizService") as quiz_service, patch(
            "app.bot.handlers.webapp.QuestionService"
        ) as question_service:
            quiz_service.return_value.detail = AsyncMock(return_value=quiz)
            question_service.return_value.list_by_quiz = AsyncMock(return_value=questions)

            payload = await quiz_review(
                quiz_id=7,
                current_user=SimpleNamespace(id=42),
                db=SimpleNamespace(),
            )

        quiz_service.return_value.detail.assert_awaited_once_with(42, 7)
        question_service.return_value.list_by_quiz.assert_awaited_once_with(7, 42)

        response = QuizReviewResponse.model_validate(payload, from_attributes=True)
        self.assertEqual(response.quiz_id, 7)
        self.assertEqual(response.title, "Algebra asoslari")
        self.assertEqual([item.id for item in response.questions], [1, 2])
        self.assertEqual(
            [entry.label for entry in response.questions[0].options if entry.is_correct],
            ["B"],
        )
        self.assertEqual(
            [entry.label for entry in response.questions[1].options if entry.is_correct],
            [],
        )

    async def test_review_propagates_owner_check_from_quiz_service(self):
        with patch("app.bot.handlers.webapp.QuizService") as quiz_service, patch(
            "app.bot.handlers.webapp.QuestionService"
        ) as question_service:
            quiz_service.return_value.detail = AsyncMock(
                side_effect=HTTPException(404, "Quiz not found")
            )
            question_service.return_value.list_by_quiz = AsyncMock()

            with self.assertRaises(HTTPException) as raised:
                await quiz_review(
                    quiz_id=7,
                    current_user=SimpleNamespace(id=42),
                    db=SimpleNamespace(),
                )

        self.assertEqual(raised.exception.status_code, 404)
        question_service.return_value.list_by_quiz.assert_not_awaited()


class ReviewCallbackFallbackTests(IsolatedAsyncioTestCase):
    def _callback(self, data: str):
        return SimpleNamespace(
            data=data,
            from_user=SimpleNamespace(id=555),
            message=SimpleNamespace(answer=AsyncMock()),
            answer=AsyncMock(),
        )

    async def test_fallback_sends_review_webapp_button_for_owner(self):
        callback = self._callback("quiz:review:7")

        with patch(
            "app.bot.handlers.quiz.user_owns_quiz", AsyncMock(return_value=True)
        ), patch(
            "app.bot.handlers.quiz.quiz_review_webapp_keyboard", return_value="keyboard"
        ) as keyboard:
            await review_generated_quiz(callback)

        keyboard.assert_called_once_with(7)
        callback.message.answer.assert_awaited_once_with(
            "Savollarni tekshirish uchun tugmani bosing.",
            reply_markup="keyboard",
        )

    async def test_fallback_rejects_quiz_of_another_user(self):
        callback = self._callback("quiz:review:7")

        with patch("app.bot.handlers.quiz.user_owns_quiz", AsyncMock(return_value=False)):
            await review_generated_quiz(callback)

        callback.message.answer.assert_not_awaited()
        callback.answer.assert_awaited_once_with(
            "Test topilmadi yoki sizga tegishli emas.", show_alert=True
        )
