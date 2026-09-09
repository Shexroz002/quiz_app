from unittest import TestCase
from unittest.mock import patch

from app.bot.keyboards.inline import generated_quiz_keyboard
from app.bot.utils.progress import (
    format_progress_text,
    format_received_text,
    progress_bar,
)


class TelegramProgressFormattingTests(TestCase):
    def test_completed_quiz_keyboard_reuses_single_and_friends_flows(self):
        with patch(
            "app.bot.keyboards.inline.quiz_webapp_url",
            return_value="https://quiz.example/bot/webapp/?quiz_id=7",
        ):
            keyboard = generated_quiz_keyboard(quiz_id=7)

        self.assertEqual(
            [row[0].text for row in keyboard.inline_keyboard],
            ["📝 Testni ishlash", "👥 Do‘stlar bilan ishlash"],
        )
        self.assertEqual(
            keyboard.inline_keyboard[0][0].web_app.url,
            "https://quiz.example/bot/webapp/?quiz_id=7",
        )
        self.assertEqual(
            keyboard.inline_keyboard[1][0].callback_data,
            "friends:quiz:duration:7:1",
        )

    def test_completed_quiz_keyboard_keeps_callback_fallback_without_https(self):
        with patch(
            "app.bot.keyboards.inline.quiz_webapp_url",
            side_effect=ValueError("HTTPS Web App URL is not available"),
        ):
            keyboard = generated_quiz_keyboard(quiz_id=7)

        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "quiz:open:7")

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
