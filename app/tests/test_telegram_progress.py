from unittest import TestCase
from unittest.mock import patch

from app.bot.keyboards.inline import (
    generated_quiz_keyboard,
    quiz_review_webapp_keyboard,
    quiz_webapp_url,
)
from app.bot.utils.progress import (
    format_progress_text,
    format_received_text,
    progress_bar,
)


def fake_webapp_url(quiz_id, duration_minutes=None, *, mode=None):
    url = f"https://quiz.example/bot/webapp/?quiz_id={quiz_id}"
    if duration_minutes is not None:
        url += f"&duration_minutes={duration_minutes}"
    if mode is not None:
        url += f"&mode={mode}"
    return url


class TelegramProgressFormattingTests(TestCase):
    def test_completed_quiz_keyboard_offers_review_before_play_flows(self):
        with patch("app.bot.keyboards.inline.quiz_webapp_url", side_effect=fake_webapp_url):
            keyboard = generated_quiz_keyboard(quiz_id=7)

        self.assertEqual(
            [row[0].text for row in keyboard.inline_keyboard],
            ["🔍 Savollarni tekshirish", "📝 Testni ishlash", "👥 Do‘stlar bilan ishlash"],
        )
        self.assertEqual(
            keyboard.inline_keyboard[0][0].web_app.url,
            "https://quiz.example/bot/webapp/?quiz_id=7&mode=review",
        )
        self.assertEqual(
            keyboard.inline_keyboard[1][0].web_app.url,
            "https://quiz.example/bot/webapp/?quiz_id=7",
        )
        self.assertEqual(
            keyboard.inline_keyboard[2][0].callback_data,
            "friends:quiz:duration:7:1",
        )

    def test_completed_quiz_keyboard_keeps_callback_fallback_without_https(self):
        with patch(
            "app.bot.keyboards.inline.quiz_webapp_url",
            side_effect=ValueError("HTTPS Web App URL is not available"),
        ):
            keyboard = generated_quiz_keyboard(quiz_id=7)

        self.assertEqual(
            [row[0].callback_data for row in keyboard.inline_keyboard],
            ["quiz:review:7", "quiz:open:7", "friends:quiz:duration:7:1"],
        )

    def test_review_webapp_url_carries_review_mode(self):
        with patch(
            "app.bot.keyboards.inline.settings.TELEGRAM_WEBAPP_URL",
            "https://quiz.example/bot/webapp/",
        ):
            self.assertEqual(
                quiz_webapp_url(7, mode="review"),
                "https://quiz.example/bot/webapp/?quiz_id=7&mode=review",
            )
            self.assertEqual(
                quiz_webapp_url(7),
                "https://quiz.example/bot/webapp/?quiz_id=7",
            )
            keyboard = quiz_review_webapp_keyboard(7)

        self.assertEqual(
            keyboard.inline_keyboard[0][0].web_app.url,
            "https://quiz.example/bot/webapp/?quiz_id=7&mode=review",
        )

    def test_completed_message_directs_user_to_review_first(self):
        text = format_progress_text(
            {"status": "completed", "progress": 100, "quiz_id": 7, "question_count": 30}
        )

        self.assertIn("savollarni tekshirib chiqing", text.lower())

    def test_received_message_is_student_friendly(self):
        text = format_received_text("algebra.pdf")

        self.assertEqual(
            text,
            "📄 Test yaratilmoqda\n\n"
            "📎 algebra.pdf\n"
            "✅ Fayl muvaffaqiyatli qabul qilindi\n\n"
            "⏳ Jarayon boshlandi...",
        )

    def test_progress_stages_never_show_raw_statuses(self):
        cases = [
            (10, "🔍 PDF tahlil qilinmoqda"),
            (40, "🧠 Savollar tayyorlanmoqda"),
            (85, "💾 Test saqlanmoqda"),
        ]

        for progress, heading in cases:
            with self.subTest(progress=progress):
                text = format_progress_text(
                    {
                        "status": "processing",
                        "progress": progress,
                        "file_name": "maktab testi.pdf",
                    }
                )
                self.assertIn(heading, text)
                self.assertIn(f"{progress_bar(progress)} {progress}%", text)
                self.assertNotIn("QUESTIONS_GENERATING", text)
                self.assertNotIn("Status:", text)

    def test_completed_message_uses_existing_quiz_data(self):
        text = format_progress_text(
            {
                "status": "completed",
                "progress": 100,
                "subject": "Matematika",
                "quiz_title": "Algebra asoslari",
                "question_count": 25,
                "quiz_id": 7,
            }
        )

        self.assertIn("🎉 Test tayyor!", text)
        self.assertIn("📚 Matematika", text)
        self.assertIn("📝 Algebra asoslari", text)
        self.assertIn("❓ 25 ta savol yaratildi", text)

    def test_failed_message_hides_technical_error(self):
        text = format_progress_text(
            {
                "status": "failed",
                "progress": 100,
                "error": "Traceback: SQLAlchemy connection exception",
            }
        )

        self.assertIn("😕 Testni yaratib bo‘lmadi", text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("SQLAlchemy", text)

    def test_failed_message_shows_safe_error(self):
        error = "AI javob berishda xatolik yuz berdi. Qayta urinib ko'ring."
        text = format_progress_text(
            {
                "status": "failed",
                "progress": 100,
                "error": error,
            }
        )

        self.assertIn(error, text)
