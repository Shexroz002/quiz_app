from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.bot.handlers.challenge import (
    CALLBACK_OWNER_ALERT,
    GROUP_ADMIN_ALERT,
    challenge_start_payload,
    challenge,
    handle_challenge_callback,
    receive_group_challenge_custom_duration,
    start_private_challenge,
)
from app.bot.keyboards.inline import (
    quiz_card_keyboard,
    quiz_catalog_pagination_keyboard,
    quiz_custom_duration_keyboard,
    quiz_duration_keyboard,
)
from app.bot.keyboards.reply import (
    MENU_FRIENDS_TEXT,
    MENU_JOIN_LIVE_SESSION_TEXT,
    MENU_RESULTS_TEXT,
    MENU_TEST_CREATE_TEXT,
    MENU_TEST_WORK_TEXT,
    MENU_TESTS_TEXT,
    main_menu_keyboard,
)


class TelegramChallengeTests(IsolatedAsyncioTestCase):
    async def test_registered_user_is_sent_to_private_configuration(self):
        bot = SimpleNamespace()
        room_message = SimpleNamespace(
            message_id=555,
            edit_reply_markup=AsyncMock(),
        )
        message = SimpleNamespace(
            bot=bot,
            chat=SimpleNamespace(id=-100123),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(return_value=room_message),
        )
        state = SimpleNamespace()

        with (
            patch(
                "app.bot.handlers.challenge.is_group_admin",
                new_callable=AsyncMock,
                return_value=True,
            ) as is_admin,
            patch(
                "app.bot.handlers.challenge.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=7, is_active=True),
            ) as get_user,
            patch(
                "app.bot.handlers.challenge.create_start_link",
                new_callable=AsyncMock,
                return_value="https://t.me/example_bot?start=challenge_target",
            ) as create_link,
        ):
            await challenge(message, state)

        get_user.assert_awaited_once_with(42)
        is_admin.assert_awaited_once_with(bot, -100123, 42)
        message.answer.assert_awaited_once()
        create_link.assert_awaited_once_with(
            bot,
            challenge_start_payload(42, -100123, 555),
        )
        keyboard = room_message.edit_reply_markup.await_args.kwargs["reply_markup"]
        self.assertEqual(
            keyboard.inline_keyboard[0][0].url,
            "https://t.me/example_bot?start=challenge_target",
        )

    async def test_private_challenge_opens_host_quiz_catalog(self):
        message = SimpleNamespace(
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock())

        with (
            patch(
                "app.bot.handlers.challenge.is_group_admin",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.bot.handlers.challenge.show_quiz_catalog",
                new_callable=AsyncMock,
            ) as show_catalog,
        ):
            handled = await start_private_challenge(
                message,
                state,
                challenge_start_payload(42, -100123, 555),
            )

        self.assertTrue(handled)
        state.update_data.assert_awaited_once_with(
            challenge_group_chat_id=-100123,
            challenge_group_message_id=555,
        )
        show_catalog.assert_awaited_once_with(
            message,
            state,
            page=1,
            challenge_owner_id=42,
        )

    async def test_tampered_private_challenge_target_is_rejected(self):
        payload = challenge_start_payload(42, -100123, 555)
        message = SimpleNamespace(
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
        )
        state = SimpleNamespace()

        handled = await start_private_challenge(
            message,
            state,
            payload.replace("-100123", "-100999"),
        )

        self.assertTrue(handled)
        message.answer.assert_awaited_once_with("Xona sozlash havolasi yaroqsiz.")

    async def test_unregistered_user_is_directed_to_private_registration(self):
        bot = SimpleNamespace()
        message = SimpleNamespace(
            bot=bot,
            chat=SimpleNamespace(id=-100123),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
        )
        state = SimpleNamespace()

        with (
            patch(
                "app.bot.handlers.challenge.is_group_admin",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.bot.handlers.challenge.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.bot.handlers.challenge.create_start_link",
                new_callable=AsyncMock,
                return_value="https://t.me/example_bot?start=challenge",
            ) as create_link,
        ):
            await challenge(message, state)

        create_link.assert_awaited_once_with(bot, "challenge")
        text = message.answer.await_args.args[0]
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        self.assertIn("shaxsiy chatda", text)
        self.assertNotIn("telefon", text.lower())
        self.assertNotIn("profil", text.lower())
        self.assertEqual(
            keyboard.inline_keyboard[0][0].url,
            "https://t.me/example_bot?start=challenge",
        )

    async def test_non_admin_cannot_open_group_configuration(self):
        bot = SimpleNamespace()
        message = SimpleNamespace(
            bot=bot,
            chat=SimpleNamespace(id=-100123),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
        )

        with (
            patch(
                "app.bot.handlers.challenge.is_group_admin",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.bot.handlers.challenge.get_user_by_telegram_id",
                new_callable=AsyncMock,
            ) as get_user,
        ):
            await challenge(message, SimpleNamespace())

        message.answer.assert_awaited_once_with(GROUP_ADMIN_ALERT)
        get_user.assert_not_awaited()

    async def test_missing_telegram_user_is_ignored(self):
        message = SimpleNamespace(from_user=None, answer=AsyncMock())

        await challenge(message, SimpleNamespace())

        message.answer.assert_not_awaited()

    async def test_other_group_member_cannot_use_configuration_callback(self):
        callback = SimpleNamespace(
            data="challenge:42:set:7:15:1",
            from_user=SimpleNamespace(id=99),
            answer=AsyncMock(),
        )

        with patch(
            "app.bot.handlers.challenge.create_room",
            new_callable=AsyncMock,
        ) as create_room:
            await handle_challenge_callback(callback, SimpleNamespace())

        callback.answer.assert_awaited_once_with(
            CALLBACK_OWNER_ALERT,
            show_alert=True,
        )
        create_room.assert_not_awaited()

    async def test_fixed_duration_creates_room_on_configuration_message(self):
        bot = SimpleNamespace()
        callback = SimpleNamespace(
            data="challenge:42:set:7:15:2",
            bot=bot,
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=42),
                message_id=777,
                edit_text=AsyncMock(),
            ),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={
                "challenge_group_chat_id": -100123,
                "challenge_group_message_id": 555,
            }),
            clear=AsyncMock(),
        )

        with (
            patch(
                "app.bot.handlers.challenge.is_group_admin",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.bot.handlers.challenge.get_telegram_user_quiz",
                new_callable=AsyncMock,
                return_value={"id": 7},
            ),
            patch(
                "app.bot.handlers.challenge.create_room",
                new_callable=AsyncMock,
            ) as create_room,
            patch(
                "app.bot.handlers.challenge.remove_catalog_messages",
                new_callable=AsyncMock,
            ),
        ):
            await handle_challenge_callback(callback, state)

        create_room.assert_awaited_once_with(bot, 42, -100123, 555, 7, 15)
        state.clear.assert_awaited_once()
        callback.answer.assert_awaited_once_with("Xona yaratildi.")

    async def test_demoted_admin_cannot_create_room_from_old_private_ui(self):
        callback = SimpleNamespace(
            data="challenge:42:set:7:15:2",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=42)),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(get_data=AsyncMock(return_value={
            "challenge_group_chat_id": -100123,
            "challenge_group_message_id": 555,
        }))

        with (
            patch(
                "app.bot.handlers.challenge.get_telegram_user_quiz",
                new_callable=AsyncMock,
                return_value={"id": 7},
            ),
            patch(
                "app.bot.handlers.challenge.is_group_admin",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.bot.handlers.challenge.create_room",
                new_callable=AsyncMock,
            ) as create_room,
        ):
            await handle_challenge_callback(callback, state)

        callback.answer.assert_awaited_once_with(
            GROUP_ADMIN_ALERT,
            show_alert=True,
        )
        create_room.assert_not_awaited()

    async def test_fixed_duration_rejects_quiz_not_owned_by_host(self):
        callback = SimpleNamespace(
            data="challenge:42:set:7:15:2",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())

        with (
            patch(
                "app.bot.handlers.challenge.is_group_admin",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.bot.handlers.challenge.get_telegram_user_quiz",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.bot.handlers.challenge.create_room",
                new_callable=AsyncMock,
            ) as create_room,
        ):
            await handle_challenge_callback(callback, state)

        create_room.assert_not_awaited()
        state.clear.assert_not_awaited()
        callback.answer.assert_awaited_once_with(
            "Test topilmadi yoki sizga tegishli emas.",
            show_alert=True,
        )

    async def test_duration_callback_reuses_shared_duration_menu(self):
        callback = SimpleNamespace(
            data="challenge:42:duration:7:2",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(),
            answer=AsyncMock(),
        )
        state = SimpleNamespace()

        with patch(
            "app.bot.handlers.challenge.show_duration_menu",
            new_callable=AsyncMock,
        ) as show_duration:
            await handle_challenge_callback(callback, state)

        show_duration.assert_awaited_once_with(
            callback,
            state,
            prefix="challenge:42:duration:",
            challenge_owner_id=42,
        )

    async def test_custom_duration_creates_room_and_removes_numeric_message(self):
        bot = SimpleNamespace()
        message = SimpleNamespace(
            bot=bot,
            chat=SimpleNamespace(id=42),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
            delete=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={
                "challenge_owner_id": 42,
                "challenge_group_chat_id": -100123,
                "challenge_group_message_id": 555,
            }),
            clear=AsyncMock(),
        )
        bot.edit_message_text = AsyncMock()

        with (
            patch(
                "app.bot.handlers.challenge.is_group_admin",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.bot.handlers.challenge.custom_duration_values",
                new_callable=AsyncMock,
                return_value=({"id": 7}, 777, 25),
            ),
            patch(
                "app.bot.handlers.challenge.create_room",
                new_callable=AsyncMock,
            ) as create_room,
        ):
            await receive_group_challenge_custom_duration(message, state)

        create_room.assert_awaited_once_with(bot, 42, -100123, 555, 7, 25)
        bot.edit_message_text.assert_awaited_once_with(
            "✅ Xona guruhda yaratildi.",
            chat_id=42,
            message_id=777,
        )
        state.clear.assert_awaited_once()
        message.delete.assert_awaited_once()
        message.answer.assert_not_awaited()


class TelegramChallengeKeyboardTests(TestCase):
    def test_main_menu_uses_compact_layout_without_placeholder_action(self):
        keyboard = main_menu_keyboard()
        rows = [
            [button.text for button in row]
            for row in keyboard.keyboard
        ]

        self.assertEqual(
            rows,
            [
                [MENU_TEST_WORK_TEXT, MENU_TEST_CREATE_TEXT],
                [MENU_TESTS_TEXT, MENU_RESULTS_TEXT],
                [MENU_FRIENDS_TEXT],
            ],
        )
        self.assertNotIn(
            MENU_JOIN_LIVE_SESSION_TEXT,
            [button_text for row in rows for button_text in row],
        )

    def test_configuration_callbacks_include_initiator_id(self):
        card = quiz_card_keyboard(7, 2, challenge_owner_id=42)
        pagination = quiz_catalog_pagination_keyboard(
            2,
            3,
            challenge_owner_id=42,
        )
        duration = quiz_duration_keyboard(7, 2, challenge_owner_id=42)
        custom = quiz_custom_duration_keyboard(7, 2, challenge_owner_id=42)

        self.assertEqual(
            card.inline_keyboard[0][0].callback_data,
            "challenge:42:duration:7:2",
        )
        self.assertEqual(
            [button.callback_data for button in pagination.inline_keyboard[0]],
            [
                "challenge:42:page:1",
                "challenge:42:current",
                "challenge:42:page:3",
            ],
        )
        self.assertEqual(
            [button.callback_data for row in duration.inline_keyboard for button in row],
            [
                "challenge:42:set:7:5:2",
                "challenge:42:set:7:15:2",
                "challenge:42:set:7:30:2",
                "challenge:42:set:7:60:2",
                "challenge:42:custom:7:2",
                "challenge:42:card:7:2",
            ],
        )
        self.assertEqual(
            custom.inline_keyboard[0][0].callback_data,
            "challenge:42:duration:7:2",
        )
