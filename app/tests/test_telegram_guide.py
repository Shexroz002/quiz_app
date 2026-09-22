from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.bot.keyboards.inline import GUIDE_PAGE, guide_keyboard, guide_url
from app.bot.keyboards.reply import MENU_GUIDE_TEXT, main_menu_keyboard


def settings_with(url):
    return patch("app.bot.keyboards.inline.settings", SimpleNamespace(
        TELEGRAM_WEBAPP_URL=url, BASE_URL="http://127.0.0.1:8000"
    ))


class GuideUrlTests(TestCase):
    def test_the_page_sits_next_to_the_mini_app_bundle(self):
        with settings_with("https://app.myedunova.uz"):
            self.assertEqual(guide_url(), f"https://app.myedunova.uz/{GUIDE_PAGE}")

    def test_a_base_path_is_kept(self):
        with settings_with("https://x.trycloudflare.com/bot/webapp/"):
            self.assertEqual(guide_url(), f"https://x.trycloudflare.com/bot/webapp/{GUIDE_PAGE}")

    def test_query_parameters_of_the_base_are_dropped(self):
        with settings_with("https://app.myedunova.uz/?v=2"):
            self.assertEqual(guide_url(), f"https://app.myedunova.uz/{GUIDE_PAGE}")

    def test_without_https_there_is_no_guide(self):
        with settings_with("http://127.0.0.1:5174"), \
             patch("app.bot.keyboards.inline._TUNNEL_LOG") as log:
            log.read_text.side_effect = OSError
            with self.assertRaises(ValueError):
                guide_url()


class MenuButtonTests(TestCase):
    def texts(self, keyboard):
        return [button.text for row in keyboard.keyboard for button in row]

    def test_the_menu_carries_the_guide_as_its_own_row(self):
        with settings_with("https://app.myedunova.uz"):
            keyboard = main_menu_keyboard()

        self.assertEqual(self.texts(keyboard)[-1], MENU_GUIDE_TEXT)
        self.assertEqual(len(keyboard.keyboard[-1]), 1)

    def test_the_button_opens_the_page_inside_telegram(self):
        with settings_with("https://app.myedunova.uz"):
            button = main_menu_keyboard().keyboard[-1][0]

        self.assertEqual(button.web_app.url, f"https://app.myedunova.uz/{GUIDE_PAGE}")

    def test_without_an_https_base_the_button_stays_but_loses_the_mini_app(self):
        # Aks holda butun menyu klaviaturasi qurilmay qolardi.
        with settings_with(None), patch("app.bot.keyboards.inline._TUNNEL_LOG") as log:
            log.read_text.side_effect = OSError
            button = main_menu_keyboard().keyboard[-1][0]

        self.assertEqual(button.text, MENU_GUIDE_TEXT)
        self.assertIsNone(button.web_app)


class GuideMessageTests(IsolatedAsyncioTestCase):
    async def _tap(self, url):
        from app.bot.handlers.menu import show_guide_from_menu

        message = SimpleNamespace(answer=AsyncMock())
        state = SimpleNamespace(set_state=AsyncMock())
        with settings_with(url), patch("app.bot.keyboards.inline._TUNNEL_LOG") as log:
            log.read_text.side_effect = OSError
            await show_guide_from_menu(message, state)
        return message

    async def test_a_plain_tap_answers_with_an_inline_button(self):
        message = await self._tap("https://app.myedunova.uz")

        keyboard = message.answer.await_args.kwargs["reply_markup"]
        button = keyboard.inline_keyboard[0][0]
        self.assertEqual(button.web_app.url, f"https://app.myedunova.uz/{GUIDE_PAGE}")
        self.assertIn("Qo'llanma", message.answer.await_args.args[0])

    async def test_a_missing_base_is_reported_instead_of_crashing(self):
        message = await self._tap(None)

        self.assertIsNone(message.answer.await_args.kwargs.get("reply_markup"))
        self.assertIn("mavjud emas", message.answer.await_args.args[0])


class GuidePageTests(TestCase):
    """Tugma ochadigan fayl haqiqatan ham bundle ichida bo'lishi kerak."""

    def test_the_page_ships_with_the_mini_app(self):
        from pathlib import Path

        page = Path("app/bot/webapp/public") / GUIDE_PAGE
        self.assertTrue(page.is_file(), f"{page} topilmadi")
        html = page.read_text()
        self.assertIn("<!doctype html>", html)
        self.assertIn("EduNova bot qo'llanmasi", html)
