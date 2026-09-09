import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import settings

MENU_TEST_WORK = "menu:test_work"
MENU_TEST_CREATE = "menu:test_create"
MENU_TESTS = "menu:tests"
MENU_RESULTS = "menu:results"
MENU_JOIN_LIVE_SESSION = "menu:join_live_session"
MENU_FRIENDS = "menu:friends"
QUIZ_OPEN = "quiz:open"
QUIZ_START = "quiz:start"
QUIZ_LIST_PAGE = "quizzes:page:"
QUIZ_DURATION_MENU = "quiz:duration:"
QUIZ_DURATION_SET = "quiz:set-duration:"
QUIZ_DURATION_CUSTOM = "quiz:custom-duration:"
QUIZ_CARD = "quiz:card:"
SINGLE_QUIZ_LIST_PAGE = "single:quizzes:page:"
SINGLE_QUIZ_DURATION_MENU = "single:quiz:duration:"
SINGLE_QUIZ_DURATION_SET = "single:quiz:set-duration:"
SINGLE_QUIZ_DURATION_CUSTOM = "single:quiz:custom-duration:"
SINGLE_QUIZ_CARD = "single:quiz:card:"
FRIENDS_QUIZ_LIST_PAGE = "friends:quizzes:page:"
FRIENDS_QUIZ_DURATION_MENU = "friends:quiz:duration:"
FRIENDS_QUIZ_DURATION_SET = "friends:quiz:set-duration:"
FRIENDS_QUIZ_DURATION_CUSTOM = "friends:quiz:custom-duration:"
FRIENDS_QUIZ_CARD = "friends:quiz:card:"
RESULTS_LIST_PAGE = "results:page:"
RESULTS_CURRENT = "results:current"

_TUNNEL_LOG = Path("/tunnel/cloudflared.log")
_QUICK_TUNNEL_PATTERN = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")


def grade_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{grade}-sinf", callback_data=f"grade:{grade}")]
        for grade in range(5, 12)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def generated_quiz_keyboard(quiz_id: int) -> InlineKeyboardMarkup:
    try:
        single_player_button = InlineKeyboardButton(
            text="📝 Testni ishlash",
            web_app=WebAppInfo(url=quiz_webapp_url(quiz_id)),
        )
    except ValueError:
        single_player_button = InlineKeyboardButton(
            text="📝 Testni ishlash",
            callback_data=f"{QUIZ_OPEN}:{quiz_id}",
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [single_player_button],
            [
                InlineKeyboardButton(
                    text="👥 Do‘stlar bilan ishlash",
                    callback_data=f"{FRIENDS_QUIZ_DURATION_MENU}{quiz_id}:1",
                )
            ],
        ]
    )


def quiz_webapp_keyboard(quiz_id: int, duration_minutes: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Testni boshlash", web_app=WebAppInfo(url=quiz_webapp_url(quiz_id, duration_minutes)))],
        ]
    )


def quiz_webapp_url(quiz_id: int, duration_minutes: int | None = None) -> str:
    webapp_base_url = settings.TELEGRAM_WEBAPP_URL
    if urlsplit(webapp_base_url or "").scheme != "https":
        try:
            tunnel_urls = _QUICK_TUNNEL_PATTERN.findall(_TUNNEL_LOG.read_text())
        except OSError:
            tunnel_urls = []
        if tunnel_urls:
            webapp_base_url = f"{tunnel_urls[-1]}/bot/webapp/"

    url = urlsplit(webapp_base_url or f"{settings.BASE_URL.rstrip('/')}/bot/webapp/")
    if url.scheme != "https":
        raise ValueError("HTTPS Web App URL is not available")
    query = dict(parse_qsl(url.query))
    query["quiz_id"] = str(quiz_id)
    if duration_minutes is not None:
        query["duration_minutes"] = str(duration_minutes)
    return urlunsplit(url._replace(query=urlencode(query)))


def quiz_catalog_pagination_keyboard(
    page: int,
    total_pages: int,
    *,
    single_player: bool = False,
    friends_mode: bool = False,
) -> InlineKeyboardMarkup:
    if single_player and friends_mode:
        raise ValueError("Quiz catalog mode must be unambiguous")
    if friends_mode:
        page_prefix = FRIENDS_QUIZ_LIST_PAGE
        current_callback = "friends:quizzes:current"
    elif single_player:
        page_prefix = SINGLE_QUIZ_LIST_PAGE
        current_callback = "single:quizzes:current"
    else:
        page_prefix = QUIZ_LIST_PAGE
        current_callback = "quizzes:current"
    navigation = []
    if page > 1:
        navigation.append(InlineKeyboardButton(text="‹ Oldingi", callback_data=f"{page_prefix}{page - 1}"))
    navigation.append(InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data=current_callback))
    if page < total_pages:
        navigation.append(InlineKeyboardButton(text="Keyingi ›", callback_data=f"{page_prefix}{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[navigation])


def result_history_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    navigation = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                text="‹ Oldingi",
                callback_data=f"{RESULTS_LIST_PAGE}{page - 1}",
            )
        )
    navigation.append(
        InlineKeyboardButton(
            text=f"{page} / {total_pages}",
            callback_data=RESULTS_CURRENT,
        )
    )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                text="Keyingi ›",
                callback_data=f"{RESULTS_LIST_PAGE}{page + 1}",
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[navigation])


def quiz_card_keyboard(
    quiz_id: int,
    page: int,
    *,
    single_player: bool = False,
    friends_mode: bool = False,
) -> InlineKeyboardMarkup:
    if single_player and friends_mode:
        raise ValueError("Quiz catalog mode must be unambiguous")
    if friends_mode:
        duration_prefix = FRIENDS_QUIZ_DURATION_MENU
    elif single_player:
        duration_prefix = SINGLE_QUIZ_DURATION_MENU
    else:
        duration_prefix = QUIZ_DURATION_MENU
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Boshlash", callback_data=f"{duration_prefix}{quiz_id}:{page}")],
        ]
    )


def quiz_duration_keyboard(
    quiz_id: int,
    page: int,
    *,
    single_player: bool = False,
    friends_mode: bool = False,
) -> InlineKeyboardMarkup:
    if single_player and friends_mode:
        raise ValueError("Quiz duration mode must be unambiguous")
    if friends_mode:
        set_prefix = FRIENDS_QUIZ_DURATION_SET
        custom_prefix = FRIENDS_QUIZ_DURATION_CUSTOM
        card_prefix = FRIENDS_QUIZ_CARD
    elif single_player:
        set_prefix = SINGLE_QUIZ_DURATION_SET
        custom_prefix = SINGLE_QUIZ_DURATION_CUSTOM
        card_prefix = SINGLE_QUIZ_CARD
    else:
        set_prefix = QUIZ_DURATION_SET
        custom_prefix = QUIZ_DURATION_CUSTOM
        card_prefix = QUIZ_CARD

    def duration_button(minutes: int) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=f"{minutes} daqiqa",
            callback_data=f"{set_prefix}{quiz_id}:{minutes}:{page}",
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [duration_button(5), duration_button(15)],
            [duration_button(30), duration_button(60)],
            [InlineKeyboardButton(text="✏️ Qo'lda kiritish", callback_data=f"{custom_prefix}{quiz_id}:{page}")],
            [InlineKeyboardButton(text="← Orqaga", callback_data=f"{card_prefix}{quiz_id}:{page}")],
        ]
    )


def quiz_custom_duration_keyboard(
    quiz_id: int,
    page: int,
    *,
    single_player: bool = False,
    friends_mode: bool = False,
) -> InlineKeyboardMarkup:
    if single_player and friends_mode:
        raise ValueError("Quiz duration mode must be unambiguous")
    if friends_mode:
        duration_prefix = FRIENDS_QUIZ_DURATION_MENU
    elif single_player:
        duration_prefix = SINGLE_QUIZ_DURATION_MENU
    else:
        duration_prefix = QUIZ_DURATION_MENU
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Vaqt tanlash", callback_data=f"{duration_prefix}{quiz_id}:{page}")],
        ]
    )
