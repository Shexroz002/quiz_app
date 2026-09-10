from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MENU_TEST_WORK_TEXT = "▶️ Test ishlash"
MENU_TEST_CREATE_TEXT = "➕ Test yaratish"
MENU_TESTS_TEXT = "📚 Testlar"
MENU_RESULTS_TEXT = "📊 Natijalar"
MENU_JOIN_LIVE_SESSION_TEXT = "📡 Jonli sessiyaga qo‘shilish"
MENU_FRIENDS_TEXT = "👥 Do‘stlar bilan ishlash"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=MENU_TEST_WORK_TEXT),
                KeyboardButton(text=MENU_TEST_CREATE_TEXT),
            ],
            [
                KeyboardButton(text=MENU_TESTS_TEXT),
                KeyboardButton(text=MENU_RESULTS_TEXT),
            ],
            [KeyboardButton(text=MENU_FRIENDS_TEXT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Kerakli bo‘limni tanlang",
    )


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Telefon raqamni yuborish", request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
