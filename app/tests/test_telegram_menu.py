from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest import TestCase
from unittest.mock import AsyncMock
from unittest.mock import patch

from app.bot.handlers.menu import (
    format_result_history,
    format_single_player_ready,
    remove_catalog_messages,
    set_friends_duration,
    set_single_player_duration,
    show_friends_quizzes,
    show_result_history,
)
from app.bot.keyboards.inline import (
    quiz_card_keyboard,
    quiz_catalog_pagination_keyboard,
    quiz_duration_keyboard,
    result_history_pagination_keyboard,
)


class TelegramMenuCatalogTests(IsolatedAsyncioTestCase):
    async def test_selection_removes_catalog_except_selected_card(self):
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={
                "quiz_catalog_header_message_id": 10,
                "quiz_catalog_card_ids": [11, 12, 13],
                "quiz_catalog_pagination_message_id": 14,
            }),
            update_data=AsyncMock(),
        )
        bot = SimpleNamespace(delete_message=AsyncMock())

        await remove_catalog_messages(
            bot,
            chat_id=99,
            state=state,
            keep_message_id=12,
            include_header=True,
        )

        deleted_ids = [call.args[1] for call in bot.delete_message.await_args_list]
        self.assertEqual(deleted_ids, [11, 13, 14, 10])
        state.update_data.assert_awaited_once_with(
            quiz_catalog_card_ids=[],
            quiz_catalog_pagination_message_id=None,
            quiz_catalog_header_message_id=None,
        )

    async def test_friends_menu_opens_shared_catalog_in_friends_mode(self):
        callback = SimpleNamespace(
            message=SimpleNamespace(message_id=10),
        )
        state = SimpleNamespace(update_data=AsyncMock())

        with patch(
            "app.bot.handlers.menu.show_quiz_catalog",
            new_callable=AsyncMock,
        ) as show_catalog:
            await show_friends_quizzes(callback, state)

        state.update_data.assert_awaited_once_with(quiz_catalog_header_message_id=10)
        show_catalog.assert_awaited_once_with(
            callback,
            state,
            page=1,
            friends_mode=True,
        )

    async def test_friends_duration_creates_room_for_owned_quiz(self):
        bot = SimpleNamespace()
        callback = SimpleNamespace(
            data="friends:quiz:set-duration:7:15:2",
            bot=bot,
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=99),
                message_id=123,
            ),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(set_state=AsyncMock())

        with (
            patch(
                "app.bot.handlers.menu.get_telegram_user_quiz",
                new_callable=AsyncMock,
                return_value={"id": 7, "question_count": 10},
            ),
            patch(
                "app.bot.handlers.menu.create_room",
                new_callable=AsyncMock,
            ) as create_room,
        ):
            await set_friends_duration(callback, state)

        create_room.assert_awaited_once_with(bot, 42, 99, 123, 7, 15)
        callback.answer.assert_awaited_once_with("Xona yaratildi.")

    async def test_friends_duration_rejects_quiz_owned_by_another_user(self):
        callback = SimpleNamespace(
            data="friends:quiz:set-duration:7:15:1",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=99),
                message_id=123,
            ),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(set_state=AsyncMock())

        with (
            patch(
                "app.bot.handlers.menu.get_telegram_user_quiz",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.bot.handlers.menu.create_room",
                new_callable=AsyncMock,
            ) as create_room,
        ):
            await set_friends_duration(callback, state)

        create_room.assert_not_awaited()
        callback.answer.assert_awaited_once_with(
            "Test topilmadi yoki sizga tegishli emas.",
            show_alert=True,
        )

    async def test_single_player_duration_never_creates_room(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(
            data="single:quiz:set-duration:7:30:1",
            from_user=SimpleNamespace(id=42),
            message=message,
            answer=AsyncMock(),
        )
        state = SimpleNamespace(set_state=AsyncMock())

        with (
            patch(
                "app.bot.handlers.menu.get_telegram_user_quiz",
                new_callable=AsyncMock,
                return_value={"id": 7, "question_count": 10},
            ),
            patch(
                "app.bot.handlers.menu.quiz_webapp_keyboard",
                return_value="single-player-keyboard",
            ),
            patch(
                "app.bot.handlers.menu.create_room",
                new_callable=AsyncMock,
            ) as create_room,
        ):
            await set_single_player_duration(callback, state)

        create_room.assert_not_awaited()
        message.edit_text.assert_awaited_once()
        ready_text = message.edit_text.await_args.args[0]
        self.assertIn("📋 <b>Test tayyor</b>", ready_text)
        self.assertIn("❔ Savollar soni: <b>10 ta</b>", ready_text)
        self.assertIn("⏱ Vaqt chegarasi: <b>30 daqiqa</b>", ready_text)
        self.assertIn("☆ Har bir to‘g‘ri javob: <b>+1 ball</b>", ready_text)
        callback.answer.assert_awaited_once_with("Test tayyor.")

    def test_single_player_ready_message_matches_quiz_summary_design(self):
        text = format_single_player_ready({"question_count": 10}, 5)

        self.assertEqual(
            text,
            "📋 <b>Test tayyor</b>\n\n"
            "❔ Savollar soni: <b>10 ta</b>\n"
            "⏱ Vaqt chegarasi: <b>5 daqiqa</b>\n"
            "☆ Har bir to‘g‘ri javob: <b>+1 ball</b>",
        )


class TelegramMenuKeyboardTests(IsolatedAsyncioTestCase):
    async def test_friends_catalog_uses_explicit_callback_namespace(self):
        card = quiz_card_keyboard(quiz_id=7, page=2, friends_mode=True)
        pagination = quiz_catalog_pagination_keyboard(
            page=2,
            total_pages=3,
            friends_mode=True,
        )
        duration = quiz_duration_keyboard(quiz_id=7, page=2, friends_mode=True)

        self.assertEqual(
            card.inline_keyboard[0][0].callback_data,
            "friends:quiz:duration:7:2",
        )
        self.assertEqual(
            [button.callback_data for button in pagination.inline_keyboard[0]],
            [
                "friends:quizzes:page:1",
                "friends:quizzes:current",
                "friends:quizzes:page:3",
            ],
        )
        self.assertEqual(
            [button.callback_data for row in duration.inline_keyboard for button in row],
            [
                "friends:quiz:set-duration:7:5:2",
                "friends:quiz:set-duration:7:15:2",
                "friends:quiz:set-duration:7:30:2",
                "friends:quiz:set-duration:7:60:2",
                "friends:quiz:custom-duration:7:2",
                "friends:quiz:card:7:2",
            ],
        )

    async def test_result_history_uses_explicit_pagination_namespace(self):
        pagination = result_history_pagination_keyboard(page=2, total_pages=3)

        self.assertEqual(
            [button.callback_data for button in pagination.inline_keyboard[0]],
            ["results:page:1", "results:current", "results:page:3"],
        )


class TelegramResultHistoryTests(IsolatedAsyncioTestCase):
    async def test_history_query_uses_registered_user_id(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=998877),
            answer=AsyncMock(),
        )
        registered_user = SimpleNamespace(id=42, is_active=True)
        result = {
            "quiz_title": "Algebra",
            "subject": "Matematika",
            "score": 7,
            "total_questions": 10,
            "started_at": datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 9, 9, 10, 2, 5, tzinfo=timezone.utc),
        }

        with (
            patch(
                "app.bot.handlers.menu.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=registered_user,
            ),
            patch(
                "app.bot.handlers.menu.get_result_history_page",
                new_callable=AsyncMock,
                return_value=([result], 1, 1),
            ) as get_history,
        ):
            await show_result_history(message, page=1)

        get_history.assert_awaited_once_with(1, 42)
        message.answer.assert_awaited_once()

    async def test_empty_history_has_clean_telegram_state(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=998877),
            answer=AsyncMock(),
        )

        with (
            patch(
                "app.bot.handlers.menu.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=42, is_active=True),
            ),
            patch(
                "app.bot.handlers.menu.get_result_history_page",
                new_callable=AsyncMock,
                return_value=([], 1, 1),
            ),
        ):
            await show_result_history(message, page=1)

        _, kwargs = message.answer.await_args
        self.assertIn("yakunlangan test natijalari yo'q", message.answer.await_args.args[0])
        self.assertIsNone(kwargs["reply_markup"])


class TelegramResultHistoryFormattingTests(TestCase):
    def test_formats_existing_attempt_values(self):
        text = format_result_history(
            [
                {
                    "quiz_title": "Algebra <Asoslari>",
                    "subject": "Math & Logic",
                    "score": 7,
                    "total_questions": 10,
                    "started_at": datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc),
                    "finished_at": datetime(2026, 9, 9, 10, 2, 5, tzinfo=timezone.utc),
                }
            ],
            page=1,
            total_pages=1,
        )

        self.assertIn("Algebra &lt;Asoslari&gt;", text)
        self.assertIn("Math &amp; Logic", text)
        self.assertIn("7 / 10", text)
        self.assertIn("70%", text)
        self.assertIn("02:05", text)
        self.assertIn("09.09.2026 15:02", text)
