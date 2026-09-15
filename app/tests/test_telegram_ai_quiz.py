from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.bot.handlers.quiz import (
    MAX_DESCRIPTION_LENGTH,
    _create_ai_quiz_job,
    load_subjects_page,
    receive_ai_description,
    receive_custom_question_count,
)
from app.bot.keyboards.inline import (
    AI_MAX_QUESTIONS,
    AI_MIN_QUESTIONS,
    ai_question_count_keyboard,
    ai_subject_keyboard,
    quiz_create_mode_keyboard,
)
from app.bot.utils.progress import format_progress_text


def subject(sid, name, icon=None):
    return SimpleNamespace(id=sid, name=name, icon=icon)


class CreateModeKeyboardTests(TestCase):
    def test_both_sources_are_offered(self):
        keyboard = quiz_create_mode_keyboard()

        self.assertEqual(
            [(row[0].text, row[0].callback_data) for row in keyboard.inline_keyboard],
            [("📄 PDF fayldan", "create:pdf"), ("✨ AI orqali", "create:ai")],
        )

    def test_subject_keyboard_has_no_pager_on_a_single_page(self):
        keyboard = ai_subject_keyboard(
            [{"id": 1, "name": "Fizika", "icon": "⚛️"}], page=1, total_pages=1
        )

        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(texts, ["⚛️ Fizika", "✖️ Bekor qilish"])
        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "ai:subject:1")

    def test_subject_keyboard_pages_when_there_are_more(self):
        keyboard = ai_subject_keyboard(
            [{"id": 3, "name": "Kimyo", "icon": "🧪"}], page=2, total_pages=3
        )

        pager = [button.callback_data for button in keyboard.inline_keyboard[1]]
        self.assertEqual(pager, ["ai:subjects:page:1", "ai:subjects:page:2", "ai:subjects:page:3"])

    def test_count_keyboard_offers_presets_and_manual_entry(self):
        texts = [b.text for row in ai_question_count_keyboard().inline_keyboard for b in row]

        self.assertEqual(texts[:4], ["10 ta", "15 ta", "20 ta", "30 ta"])
        self.assertIn("✏️ Qo‘lda kiritish", texts)


class SubjectPagingTests(IsolatedAsyncioTestCase):
    async def _page(self, subjects, page):
        with patch("app.bot.handlers.quiz.SubjectService") as service, patch(
            "app.bot.handlers.quiz.AsyncSessionLocal"
        ) as factory:
            factory.return_value.__aenter__ = AsyncMock(return_value=SimpleNamespace())
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            service.return_value.list = AsyncMock(return_value=subjects)
            return await load_subjects_page(page)

    async def test_missing_icon_falls_back_to_the_subject_icon_map(self):
        rows, page, total_pages, total = await self._page([subject(2, "Matematika")], 1)

        self.assertEqual(rows[0]["icon"], "📐")
        self.assertEqual((page, total_pages, total), (1, 1, 1))

    async def test_stored_icon_wins_over_the_map(self):
        rows, *_ = await self._page([subject(2, "Matematika", "🧮")], 1)

        self.assertEqual(rows[0]["icon"], "🧮")

    async def test_pages_are_capped_to_the_available_range(self):
        subjects = [subject(index, f"Fan {index}") for index in range(1, 12)]

        rows, page, total_pages, total = await self._page(subjects, 9)

        self.assertEqual((page, total_pages, total), (2, 2, 11))
        self.assertEqual(len(rows), 3)

    async def test_empty_subject_table_reports_zero(self):
        rows, page, total_pages, total = await self._page([], 1)

        self.assertEqual((rows, page, total_pages, total), ([], 1, 1, 0))


class DescriptionValidationTests(IsolatedAsyncioTestCase):
    async def _send(self, text):
        message = SimpleNamespace(text=text, answer=AsyncMock())
        state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
        await receive_ai_description(message, state)
        return message, state

    async def test_too_short_description_is_rejected(self):
        message, state = await self._send("ab")

        state.update_data.assert_not_awaited()
        self.assertIn("qisqa", message.answer.await_args.args[0])

    async def test_too_long_description_is_rejected(self):
        message, state = await self._send("x" * (MAX_DESCRIPTION_LENGTH + 1))

        state.update_data.assert_not_awaited()
        self.assertIn("uzun", message.answer.await_args.args[0])

    async def test_valid_description_advances_to_the_count_step(self):
        message, state = await self._send("  Aritmetik progressiya  ")

        state.update_data.assert_awaited_once_with(ai_description="Aritmetik progressiya")
        state.set_state.assert_awaited_once()
        self.assertIsNotNone(message.answer.await_args.kwargs["reply_markup"])


class CustomCountValidationTests(IsolatedAsyncioTestCase):
    async def _send(self, text):
        message = SimpleNamespace(text=text, answer=AsyncMock())
        state = SimpleNamespace(get_data=AsyncMock(return_value={}), clear=AsyncMock())
        with patch("app.bot.handlers.quiz._create_ai_quiz_job", AsyncMock()) as create:
            await receive_custom_question_count(message, state, SimpleNamespace())
        return message, create

    async def test_non_numeric_input_is_rejected(self):
        message, create = await self._send("yigirma")

        create.assert_not_awaited()
        self.assertIn("Faqat son", message.answer.await_args.args[0])

    async def test_out_of_range_count_is_rejected(self):
        for value in (AI_MIN_QUESTIONS - 1, AI_MAX_QUESTIONS + 1):
            with self.subTest(value=value):
                message, create = await self._send(str(value))

                create.assert_not_awaited()
                self.assertIn("orasida", message.answer.await_args.args[0])

    async def test_valid_count_creates_the_job(self):
        _, create = await self._send(str(AI_MAX_QUESTIONS))

        self.assertEqual(create.await_args.args[3], AI_MAX_QUESTIONS)


class CreateAiJobTests(IsolatedAsyncioTestCase):
    def _message(self):
        return SimpleNamespace(
            chat=SimpleNamespace(id=500),
            answer=AsyncMock(return_value=SimpleNamespace(message_id=11, edit_text=AsyncMock())),
        )

    async def _run(self, data, *, user=SimpleNamespace(id=7), service_error=None):
        message = self._message()
        state = SimpleNamespace(get_data=AsyncMock(return_value=data), clear=AsyncMock())
        job = SimpleNamespace(
            id="job-1", status=SimpleNamespace(value="queued"), progress=0,
            message="...", file_name=None, description=data.get("ai_description"),
            number_questions=20,
        )
        create = AsyncMock(side_effect=service_error) if service_error else AsyncMock(return_value=job)

        with patch("app.bot.handlers.quiz.get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch("app.bot.handlers.quiz.AsyncSessionLocal") as factory, \
             patch("app.bot.handlers.quiz._pdf_job_service") as job_service, \
             patch("app.bot.handlers.quiz._watch_job", AsyncMock()) as watch:
            factory.return_value.__aenter__ = AsyncMock(return_value=SimpleNamespace())
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            job_service.return_value.create_job_by_description = create
            await _create_ai_quiz_job(message, state, SimpleNamespace(), 20)
        return message, state, create, watch

    async def test_job_is_created_with_the_collected_answers(self):
        _, state, create, watch = await self._run(
            {"ai_subject_id": 2, "ai_description": "Aritmetik progressiya"}
        )

        create.assert_awaited_once_with(
            subject=2, description="Aritmetik progressiya", question_count=20, user_id=7
        )
        watch.assert_awaited_once()
        state.clear.assert_awaited_once()

    async def test_unregistered_user_is_sent_to_start(self):
        message, state, create, _ = await self._run({}, user=None)

        create.assert_not_awaited()
        self.assertIn("/start", message.answer.await_args.args[0])
        state.clear.assert_awaited_once()

    async def test_lost_state_asks_the_user_to_start_over(self):
        message, state, create, _ = await self._run({"ai_subject_id": 2})

        create.assert_not_awaited()
        self.assertIn("qaytadan", message.answer.await_args.args[0])

    async def test_service_failure_reports_it_on_the_status_message(self):
        from fastapi import HTTPException

        message, state, _, watch = await self._run(
            {"ai_subject_id": 2, "ai_description": "Mavzu"},
            service_error=HTTPException(400, "Limit tugadi"),
        )

        watch.assert_not_awaited()
        status_message = message.answer.return_value
        self.assertIn("Limit tugadi", status_message.edit_text.await_args.args[0])
        state.clear.assert_awaited_once()


class AiProgressTextTests(TestCase):
    AI_JOB = {"status": "processing", "description": "Aritmetik progressiya", "number_questions": 20}

    def test_no_ai_stage_ever_mentions_a_pdf(self):
        for progress in (0, 10, 40, 90):
            with self.subTest(progress=progress):
                self.assertNotIn("PDF", format_progress_text({**self.AI_JOB, "progress": progress}))

    def test_stages_that_show_a_source_show_the_topic(self):
        # The saving stage is deliberately source-agnostic for both job kinds.
        for progress in (0, 10, 40):
            with self.subTest(progress=progress):
                text = format_progress_text({**self.AI_JOB, "progress": progress})

                self.assertIn("📝 Aritmetik progressiya", text)
                self.assertIn("❓ 20 ta savol", text)

    def test_pdf_stages_are_unchanged(self):
        text = format_progress_text({"status": "processing", "progress": 10, "file_name": "algebra.pdf"})

        self.assertIn("🔍 PDF tahlil qilinmoqda", text)
        self.assertIn("📎 algebra.pdf", text)

    def test_failed_ai_job_blames_the_topic_not_the_file(self):
        text = format_progress_text({**self.AI_JOB, "status": "failed", "progress": 100})

        self.assertIn("Mavzu bo‘yicha test yaratishda muammo", text)
        self.assertNotIn("PDF faylni", text)

    def test_long_description_is_trimmed(self):
        text = format_progress_text({**self.AI_JOB, "progress": 40, "description": "x" * 200})

        self.assertIn("...", text)
        self.assertNotIn("x" * 100, text)

    def test_completed_ai_job_uses_the_shared_ready_message(self):
        text = format_progress_text(
            {**self.AI_JOB, "status": "completed", "progress": 100,
             "quiz_id": 5, "question_count": 20, "quiz_title": "Progressiya", "subject": "Matematika"}
        )

        self.assertIn("🎉 Test tayyor!", text)
        self.assertIn("❓ 20 ta savol yaratildi", text)
