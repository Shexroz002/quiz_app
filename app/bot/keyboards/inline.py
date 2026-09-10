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
CHALLENGE_CALLBACK_PREFIX = "challenge:"

_TUNNEL_LOG = Path("/tunnel/cloudflared.log")
_QUICK_TUNNEL_PATTERN = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")


def challenge_callback(owner_id: int, action: str, *values: int) -> str:
    parts = (CHALLENGE_CALLBACK_PREFIX.removesuffix(":"), str(owner_id), action)
    return ":".join((*parts, *(str(value) for value in values)))


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
    challenge_owner_id: int | None = None,
) -> InlineKeyboardMarkup:
    if sum((single_player, friends_mode, challenge_owner_id is not None)) > 1:
        raise ValueError("Quiz catalog mode must be unambiguous")
    if challenge_owner_id is not None:
        page_prefix = f"{challenge_callback(challenge_owner_id, 'page')}:"
        current_callback = challenge_callback(challenge_owner_id, "current")
    elif friends_mode:
        page_prefix = FRIENDS_QUIZ_LIST_PAGE
        current_callback = "friends:quizzes:current"
    elif single_player:
        page_prefix = SINGLE_QUIZ_LIST_PAGE
        current_callback = "single:quizzes:current"
    else:
        page_prefix = QUIZ_LIST_PAGE
        current_callback = "quizzes:current"

    def page_callback(target_page: int) -> str:
        return f"{page_prefix}{target_page}"

    navigation = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                text="‹ Oldingi",
                callback_data=page_callback(page - 1),
            )
        )
    navigation.append(
        InlineKeyboardButton(
            text=f"{page} / {total_pages}",
            callback_data=current_callback,
        )
    )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                text="Keyingi ›",
                callback_data=page_callback(page + 1),
            )
        )
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
    challenge_owner_id: int | None = None,
) -> InlineKeyboardMarkup:
    if sum((single_player, friends_mode, challenge_owner_id is not None)) > 1:
        raise ValueError("Quiz catalog mode must be unambiguous")
    if challenge_owner_id is not None:
        callback_data = challenge_callback(
            challenge_owner_id,
            "duration",
            quiz_id,
            page,
        )
    elif friends_mode:
        duration_prefix = FRIENDS_QUIZ_DURATION_MENU
        callback_data = f"{duration_prefix}{quiz_id}:{page}"
    elif single_player:
        duration_prefix = SINGLE_QUIZ_DURATION_MENU
        callback_data = f"{duration_prefix}{quiz_id}:{page}"
    else:
        duration_prefix = QUIZ_DURATION_MENU
        callback_data = f"{duration_prefix}{quiz_id}:{page}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Boshlash", callback_data=callback_data)],
        ]
    )


def quiz_duration_keyboard(
    quiz_id: int,
    page: int,
    *,
    single_player: bool = False,
    friends_mode: bool = False,
    challenge_owner_id: int | None = None,
) -> InlineKeyboardMarkup:
    if sum((single_player, friends_mode, challenge_owner_id is not None)) > 1:
        raise ValueError("Quiz duration mode must be unambiguous")
    if challenge_owner_id is not None:
        set_prefix = f"{challenge_callback(challenge_owner_id, 'set')}:"
        custom_prefix = f"{challenge_callback(challenge_owner_id, 'custom')}:"
        card_prefix = f"{challenge_callback(challenge_owner_id, 'card')}:"
    elif friends_mode:
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

    def set_callback(minutes: int) -> str:
        return f"{set_prefix}{quiz_id}:{minutes}:{page}"

    custom_callback = f"{custom_prefix}{quiz_id}:{page}"
    card_callback = f"{card_prefix}{quiz_id}:{page}"

    def duration_button(minutes: int) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=f"{minutes} daqiqa",
            callback_data=set_callback(minutes),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [duration_button(5), duration_button(15)],
            [duration_button(30), duration_button(60)],
            [
                InlineKeyboardButton(
                    text="✏️ Qo'lda kiritish",
                    callback_data=custom_callback,
                )
            ],
            [InlineKeyboardButton(text="← Orqaga", callback_data=card_callback)],
        ]
    )


def quiz_custom_duration_keyboard(
    quiz_id: int,
    page: int,
    *,
    single_player: bool = False,
    friends_mode: bool = False,
    challenge_owner_id: int | None = None,
) -> InlineKeyboardMarkup:
    if sum((single_player, friends_mode, challenge_owner_id is not None)) > 1:
        raise ValueError("Quiz duration mode must be unambiguous")
    if challenge_owner_id is not None:
        callback_data = challenge_callback(
            challenge_owner_id, "duration", quiz_id, page
        )
    elif friends_mode:
        duration_prefix = FRIENDS_QUIZ_DURATION_MENU
        callback_data = f"{duration_prefix}{quiz_id}:{page}"
    elif single_player:
        duration_prefix = SINGLE_QUIZ_DURATION_MENU
        callback_data = f"{duration_prefix}{quiz_id}:{page}"
    else:
        duration_prefix = QUIZ_DURATION_MENU
        callback_data = f"{duration_prefix}{quiz_id}:{page}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Vaqt tanlash", callback_data=callback_data)],
        ]
    )
