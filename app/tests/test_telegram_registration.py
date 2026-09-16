from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.bot.handlers.start import finish_registration, receive_contact, toggle_subject
from app.bot.keyboards.inline import (
    REG_SUBJECT_DONE,
    REG_SUBJECT_TOGGLE,
    registration_subject_keyboard,
)
from app.bot.states import RegistrationState

SUBJECTS = [
    {"id": 1, "name": "Fizika", "icon": "⚛️"},
    {"id": 2, "name": "Matematika", "icon": "📐"},
    {"id": 3, "name": "Kimyo", "icon": "🧪"},
]


def texts(keyboard):
    return [button.text for row in keyboard.inline_keyboard for button in row]


class SubjectKeyboardTests(TestCase):
    def test_nothing_selected_asks_for_at_least_one(self):
        keyboard = registration_subject_keyboard(SUBJECTS, [])

        self.assertEqual(texts(keyboard)[-1], "Kamida bitta fan tanlang")
        self.assertTrue(all(label.startswith("▫️") for label in texts(keyboard)[:-1]))

    def test_selected_subjects_are_ticked_and_counted(self):
        keyboard = registration_subject_keyboard(SUBJECTS, [1, 3])

        labels = texts(keyboard)
        self.assertTrue(labels[0].startswith("✅"))
        self.assertTrue(labels[1].startswith("▫️"))
        self.assertTrue(labels[2].startswith("✅"))
        self.assertEqual(labels[-1], "Tasdiqlash (2)")

    def test_every_row_carries_its_subject_id(self):
        keyboard = registration_subject_keyboard(SUBJECTS, [])

        callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
        self.assertEqual(callbacks[:-1], [f"{REG_SUBJECT_TOGGLE}{n}" for n in (1, 2, 3)])
        self.assertEqual(callbacks[-1], REG_SUBJECT_DONE)


class ContactStepTests(IsolatedAsyncioTestCase):
    async def _send(self, subjects, user=None):
        message = SimpleNamespace(
            contact=SimpleNamespace(user_id=500, phone_number="+998901112233"),
            from_user=SimpleNamespace(id=500),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock(), clear=AsyncMock())
        with patch("app.bot.handlers.start.get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch("app.bot.handlers.start.load_subjects", AsyncMock(return_value=subjects)), \
             patch("app.bot.handlers.start.show_main_menu", AsyncMock()):
            await receive_contact(message, state)
        return message, state

    async def test_contact_leads_to_the_subject_picker(self):
        message, state = await self._send(SUBJECTS)

        state.set_state.assert_awaited_once_with(RegistrationState.waiting_for_subjects)
        state.update_data.assert_awaited_once_with(
            phone_number="+998901112233", selected_subject_ids=[]
        )
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(texts(keyboard)[-1], "Kamida bitta fan tanlang")

    async def test_an_empty_catalogue_stops_instead_of_showing_no_buttons(self):
        message, state = await self._send([])

        state.set_state.assert_not_awaited()
        self.assertIn("Fanlar ro'yxati", message.answer.await_args.args[0])


class ToggleSubjectTests(IsolatedAsyncioTestCase):
    async def _toggle(self, data, selected):
        callback = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            message=SimpleNamespace(edit_reply_markup=AsyncMock()),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"selected_subject_ids": list(selected)}),
            update_data=AsyncMock(),
        )
        with patch("app.bot.handlers.start.load_subjects", AsyncMock(return_value=SUBJECTS)):
            await toggle_subject(callback, state)
        return callback, state

    async def test_tapping_an_unselected_subject_adds_it(self):
        _, state = await self._toggle(f"{REG_SUBJECT_TOGGLE}2", [])

        state.update_data.assert_awaited_once_with(selected_subject_ids=[2])

    async def test_tapping_a_selected_subject_removes_it(self):
        _, state = await self._toggle(f"{REG_SUBJECT_TOGGLE}2", [1, 2])

        state.update_data.assert_awaited_once_with(selected_subject_ids=[1])

    async def test_a_subject_removed_from_the_catalogue_drops_out_of_the_selection(self):
        _, state = await self._toggle(f"{REG_SUBJECT_TOGGLE}1", [1, 99])

        # 99 endi katalogda yo'q: u tanlovdan ham chiqib ketadi.
        state.update_data.assert_awaited_once_with(selected_subject_ids=[])

    async def test_an_unknown_subject_is_rejected(self):
        callback, state = await self._toggle(f"{REG_SUBJECT_TOGGLE}42", [])

        state.update_data.assert_not_awaited()
        callback.answer.assert_awaited_once_with("Bu fan topilmadi.", show_alert=True)

    async def test_the_keyboard_is_redrawn_with_the_new_selection(self):
        callback, _ = await self._toggle(f"{REG_SUBJECT_TOGGLE}3", [])

        keyboard = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
        self.assertEqual(texts(keyboard)[-1], "Tasdiqlash (1)")


class FinishRegistrationTests(IsolatedAsyncioTestCase):
    def _callback(self):
        return SimpleNamespace(
            from_user=SimpleNamespace(id=500),
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock(), edit_reply_markup=AsyncMock()),
        )

    async def _finish(self, selected, *, user=None, error=None):
        callback = self._callback()
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={
                "telegram_id": "500",
                "first_name": "Ali",
                "last_name": "Valiyev",
                "phone_number": "+998901112233",
                "selected_subject_ids": selected,
            }),
            clear=AsyncMock(),
        )
        register = AsyncMock(side_effect=error) if error else AsyncMock()
        with patch("app.bot.handlers.start.get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch("app.bot.handlers.start.save_telegram_profile_photo", AsyncMock(return_value=None)), \
             patch("app.bot.handlers.start.register_telegram_student", register), \
             patch("app.bot.handlers.start.show_main_menu", AsyncMock()):
            await finish_registration(callback, state, SimpleNamespace())
        return callback, state, register

    async def test_registration_stores_the_picked_subjects(self):
        _, state, register = await self._finish([2, 1])

        self.assertEqual(register.await_args.kwargs["subject_ids"], [2, 1])
        self.assertEqual(register.await_args.kwargs["phone_number"], "+998901112233")
        self.assertNotIn("grade", register.await_args.kwargs)
        state.clear.assert_awaited_once()

    async def test_confirming_with_nothing_selected_is_refused(self):
        callback, _, register = await self._finish([])

        register.assert_not_awaited()
        callback.answer.assert_awaited_once_with("Kamida bitta fan tanlang.", show_alert=True)

    async def test_a_phone_already_linked_elsewhere_is_reported(self):
        from app.bot.utils.registration import RegistrationConflictError

        callback, _, _ = await self._finish(
            [1], error=RegistrationConflictError("Bu telefon raqam boshqa akkauntga ulangan.")
        )

        self.assertIn("boshqa akkauntga", callback.message.answer.await_args.args[0])


class DisplayIconTests(TestCase):
    """subjects.icon veb frontend uchun lucide nomlarini saqlaydi ("zap"),
    Telegram esa ularni matn sifatida chiqarardi."""

    def test_web_icon_names_never_reach_a_button(self):
        from app.bot.utils.subjects import _display_icon

        for stored, name, expected in (
            ("zap", "Fizika", "⚛️"),
            ("calculator", "Matematika", "📐"),
            ("graduate", "Ona tili va adabiyoti", "📖"),
            ("leaf", "Geografiya", "🌍"),
        ):
            with self.subTest(stored=stored):
                self.assertEqual(_display_icon(stored, name), expected)

    def test_a_real_emoji_in_the_database_is_kept(self):
        from app.bot.utils.subjects import _display_icon

        self.assertEqual(_display_icon("🧮", "Matematika"), "🧮")

    def test_empty_and_unknown_fall_back(self):
        from app.bot.utils.subjects import _display_icon

        self.assertEqual(_display_icon(None, "Fizika"), "⚛️")
        self.assertEqual(_display_icon("   ", "Fizika"), "⚛️")
        self.assertEqual(_display_icon("book", "Chizmachilik"), "📘")
