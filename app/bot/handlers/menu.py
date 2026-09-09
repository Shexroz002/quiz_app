from html import escape
from math import ceil

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fastapi import HTTPException
from sqlalchemy import func, select

from app.bot.keyboards.inline import (
    FRIENDS_QUIZ_CARD,
    FRIENDS_QUIZ_DURATION_CUSTOM,
    FRIENDS_QUIZ_DURATION_MENU,
    FRIENDS_QUIZ_DURATION_SET,
    FRIENDS_QUIZ_LIST_PAGE,
    MENU_FRIENDS,
    MENU_JOIN_LIVE_SESSION,
    MENU_RESULTS,
    MENU_TEST_CREATE,
    MENU_TEST_WORK,
    MENU_TESTS,
    RESULTS_CURRENT,
    RESULTS_LIST_PAGE,
    SINGLE_QUIZ_CARD,
    SINGLE_QUIZ_DURATION_CUSTOM,
    SINGLE_QUIZ_DURATION_MENU,
    SINGLE_QUIZ_DURATION_SET,
    SINGLE_QUIZ_LIST_PAGE,
    quiz_card_keyboard,
    quiz_catalog_pagination_keyboard,
    quiz_custom_duration_keyboard,
    quiz_duration_keyboard,
    result_history_pagination_keyboard,
    quiz_webapp_keyboard,
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
from app.bot.states import QuizDurationState, QuizGenerationState
from app.bot.services.quiz_room import create_room, parse_duration
from app.bot.utils.registration import get_user_by_telegram_id
from app.core.database.base import AsyncSessionLocal
from app.models.quiz import Question, Quiz
from app.models.quiz.real_time_quiz import QuizAttempt, QuizSession, SessionParticipant
from app.repositories.quiz.quiz_repo import QuizRepository
from app.utils.datetime import as_tashkent_datetime

router = Router()
QUIZZES_PER_PAGE = 5
RESULTS_PER_PAGE = 5

MENU_MESSAGES = {
    MENU_JOIN_LIVE_SESSION: "Jonli sessiyaga qo'shilish bo'limi hozircha tayyorlanmoqda.",
}

MENU_TEXT_MESSAGES = {
    MENU_JOIN_LIVE_SESSION_TEXT: MENU_MESSAGES[MENU_JOIN_LIVE_SESSION],
}

SUBJECT_ICONS = {
    "matematika": "📐",
    "algebra": "📐",
    "geometriya": "📐",
    "fizika": "⚛️",
    "kimyo": "🧪",
    "biologiya": "🧬",
    "tarix": "🏛️",
    "ingliz": "🔤",
}


def parse_callback_values(data: str | None, prefix: str, count: int) -> tuple[int, ...] | None:
    values = (data or "").removeprefix(prefix).split(":")
    if len(values) != count or any(not value.isdigit() for value in values):
        return None
    return tuple(int(value) for value in values)


async def get_quiz_catalog_page(page: int, user_id: int):
    async with AsyncSessionLocal() as db:
        total = (
            await db.execute(
                select(func.count(Quiz.id)).where(Quiz.user_id == user_id)
            )
        ).scalar_one()
        total_pages = max(1, ceil(total / QUIZZES_PER_PAGE))
        page = min(max(page, 1), total_pages)
        stmt = (
            select(
                Quiz.id,
                Quiz.title,
                Quiz.subject,
                func.count(Question.id).label("question_count"),
            )
            .outerjoin(Question, Question.quiz_id == Quiz.id)
            .where(Quiz.user_id == user_id)
            .group_by(Quiz.id)
            .order_by(Quiz.created_at.desc())
            .offset((page - 1) * QUIZZES_PER_PAGE)
            .limit(QUIZZES_PER_PAGE)
        )
        quizzes = (await db.execute(stmt)).mappings().all()
    return quizzes, page, total_pages


async def get_quiz_card(quiz_id: int, user_id: int):
    async with AsyncSessionLocal() as db:
        repo = QuizRepository(db)
        quiz = await repo.get(quiz_id, user_id)
        if quiz is None:
            return None
        return {
            "id": quiz.id,
            "title": quiz.title,
            "subject": quiz.subject,
            "question_count": await repo.quiz_question_count(quiz.id) or 0,
        }


async def get_result_history_page(page: int, user_id: int):
    async with AsyncSessionLocal() as db:
        completed_attempts = (
            QuizAttempt.finished.is_(True),
            SessionParticipant.user_id == user_id,
        )
        total = (
            await db.execute(
                select(func.count(QuizAttempt.id))
                .select_from(QuizAttempt)
                .join(
                    SessionParticipant,
                    (SessionParticipant.id == QuizAttempt.participant_id)
                    & (SessionParticipant.session_id == QuizAttempt.session_id),
                )
                .where(*completed_attempts)
            )
        ).scalar_one()
        total_pages = max(1, ceil(total / RESULTS_PER_PAGE))
        page = min(max(page, 1), total_pages)
        stmt = (
            select(
                QuizAttempt.id.label("attempt_id"),
                QuizAttempt.score,
                QuizAttempt.total_questions,
                QuizAttempt.finished_at,
                QuizSession.started_at,
                Quiz.title.label("quiz_title"),
                Quiz.subject,
            )
            .select_from(QuizAttempt)
            .join(
                SessionParticipant,
                (SessionParticipant.id == QuizAttempt.participant_id)
                & (SessionParticipant.session_id == QuizAttempt.session_id),
            )
            .join(
                QuizSession,
                QuizSession.id == QuizAttempt.session_id,
            )
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(*completed_attempts)
            .order_by(QuizAttempt.finished_at.desc().nullslast(), QuizAttempt.id.desc())
            .offset((page - 1) * RESULTS_PER_PAGE)
            .limit(RESULTS_PER_PAGE)
        )
        results = (await db.execute(stmt)).mappings().all()
    return results, page, total_pages


async def get_telegram_user_quiz(telegram_id: int, quiz_id: int):
    user = await get_user_by_telegram_id(telegram_id)
    if user is None or not user.is_active:
        return None
    return await get_quiz_card(quiz_id, user.id)


def subject_icon(subject: str | None) -> str:
    normalized_subject = (subject or "").lower()
    return next(
        (icon for keyword, icon in SUBJECT_ICONS.items() if keyword in normalized_subject),
        "📘",
    )


def format_quiz_card(quiz) -> str:
    subject = quiz["subject"] or "Fan ko'rsatilmagan"
    title = quiz["title"] or "Nomsiz test"
    return (
        f"{subject_icon(subject)} <b>{escape(subject)}</b>\n\n"
        f"<b>{escape(title)}</b>\n"
        f"📝 {quiz['question_count']} ta savol"
    )


def format_single_player_ready(quiz, minutes: int) -> str:
    return (
        "📋 <b>Test tayyor</b>\n\n"
        f"❔ Savollar soni: <b>{quiz['question_count']} ta</b>\n"
        f"⏱ Vaqt chegarasi: <b>{minutes} daqiqa</b>\n"
        "☆ Har bir to‘g‘ri javob: <b>+1 ball</b>"
    )


def format_spent_time(started_at, finished_at) -> str | None:
    if started_at is None or finished_at is None:
        return None
    seconds = max(
        0,
        int(
            (
                as_tashkent_datetime(finished_at)
                - as_tashkent_datetime(started_at)
            ).total_seconds()
        ),
    )
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02}:{seconds:02}"


def format_result_history(results, page: int, total_pages: int) -> str:
    lines = [f"📊 <b>Natijalar</b> · {page}/{total_pages}"]
    for index, result in enumerate(results, start=(page - 1) * RESULTS_PER_PAGE + 1):
        score = result["score"] or 0
        total_questions = result["total_questions"] or 0
        percentage = round(score * 100 / total_questions, 1) if total_questions else 0
        subject = result["subject"] or "Fan ko'rsatilmagan"
        lines.extend(
            [
                "",
                f"<b>{index}. {escape((result['quiz_title'] or 'Nomsiz test')[:180])}</b>",
                f"📚 {escape(subject[:80])}",
                f"🎯 <b>{score} / {total_questions}</b> ({percentage:g}%)",
            ]
        )
        spent_time = format_spent_time(result["started_at"], result["finished_at"])
        if spent_time is not None:
            lines.append(f"⏱ {spent_time}")
        if result["finished_at"] is not None:
            completed_at = as_tashkent_datetime(result["finished_at"])
            lines.append(f"📅 {completed_at:%d.%m.%Y %H:%M}")
    return "\n".join(lines)


async def show_result_history(event: CallbackQuery | Message, page: int) -> None:
    if event.from_user is None:
        return
    user = await get_user_by_telegram_id(event.from_user.id)
    if user is None or not user.is_active:
        if isinstance(event, CallbackQuery):
            await event.answer("Avval /start orqali ro'yxatdan o'ting.", show_alert=True)
        else:
            await event.answer("Avval /start orqali ro'yxatdan o'ting.")
        return

    results, current_page, total_pages = await get_result_history_page(page, user.id)
    if results:
        text = format_result_history(results, current_page, total_pages)
        keyboard = result_history_pagination_keyboard(current_page, total_pages)
    else:
        text = (
            "📊 <b>Natijalar</b>\n\n"
            "Sizda hozircha yakunlangan test natijalari yo'q."
        )
        keyboard = None

    if isinstance(event, CallbackQuery):
        if event.message is None:
            await event.answer("Xabar topilmadi.", show_alert=True)
            return
        await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def remove_catalog_messages(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    *,
    keep_message_id: int | None = None,
    include_header: bool = False,
) -> None:
    data = await state.get_data()
    message_ids = list(data.get("quiz_catalog_card_ids", []))
    pagination_message_id = data.get("quiz_catalog_pagination_message_id")
    if isinstance(pagination_message_id, int):
        message_ids.append(pagination_message_id)
    header_message_id = data.get("quiz_catalog_header_message_id")
    if include_header and isinstance(header_message_id, int):
        message_ids.append(header_message_id)

    for message_id in dict.fromkeys(message_ids):
        if message_id == keep_message_id:
            continue
        try:
            await bot.delete_message(chat_id, message_id)
        except TelegramBadRequest:
            pass
    updates = dict(
        quiz_catalog_card_ids=[],
        quiz_catalog_pagination_message_id=None,
    )
    if include_header:
        updates["quiz_catalog_header_message_id"] = None
    await state.update_data(**updates)


async def edit_catalog_header(bot: Bot, chat_id: int, message_id: int, text: str) -> None:
    try:
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="HTML",
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


async def show_quiz_catalog(
    event: CallbackQuery | Message,
    state: FSMContext,
    page: int,
    *,
    single_player: bool = False,
    friends_mode: bool = False,
) -> None:
    if isinstance(event, CallbackQuery):
        if event.message is None:
            await event.answer("Xabar topilmadi.", show_alert=True)
            return
        message = event.message
    else:
        message = event

    if event.from_user is None:
        return
    user = await get_user_by_telegram_id(event.from_user.id)
    if user is None or not user.is_active:
        if isinstance(event, CallbackQuery):
            await event.answer("Avval /start orqali ro'yxatdan o'ting.", show_alert=True)
        else:
            await event.answer("Avval /start orqali ro'yxatdan o'ting.")
        return
    if isinstance(event, CallbackQuery):
        await event.answer()

    quizzes, current_page, total_pages = await get_quiz_catalog_page(page, user.id)
    bot = event.bot
    chat_id = message.chat.id
    data = await state.get_data()
    if isinstance(event, CallbackQuery):
        header_message_id = data.get("quiz_catalog_header_message_id", message.message_id)
        if not isinstance(header_message_id, int):
            header_message_id = message.message_id
    else:
        header_message = await event.answer("📚 <b>Testlar</b>", parse_mode="HTML")
        header_message_id = header_message.message_id

    if not quizzes:
        await edit_catalog_header(
            bot,
            chat_id,
            header_message_id,
            "📚 <b>Testlar</b>\n\nSiz hali test yaratmagansiz.",
        )
        await remove_catalog_messages(bot, chat_id, state)
        await state.update_data(quiz_catalog_header_message_id=header_message_id)
        return

    await edit_catalog_header(
        bot,
        chat_id,
        header_message_id,
        f"📚 <b>Testlar</b> · {current_page}/{total_pages}\n"
        "Quyidagilardan birini tanlang.",
    )
    await remove_catalog_messages(bot, chat_id, state)
    card_message_ids = []
    for quiz in quizzes:
        card_message = await bot.send_message(
            chat_id,
            format_quiz_card(quiz),
            reply_markup=quiz_card_keyboard(
                quiz["id"],
                current_page,
                single_player=single_player,
                friends_mode=friends_mode,
            ),
            parse_mode="HTML",
        )
        card_message_ids.append(card_message.message_id)
    pagination_message = await bot.send_message(
        chat_id,
        "📄 Sahifa",
        reply_markup=quiz_catalog_pagination_keyboard(
            current_page,
            total_pages,
            single_player=single_player,
            friends_mode=friends_mode,
        ),
    )
    await state.update_data(
        quiz_catalog_header_message_id=header_message_id,
        quiz_catalog_card_ids=card_message_ids,
        quiz_catalog_pagination_message_id=pagination_message.message_id,
    )


async def show_main_menu(message: Message) -> None:
    await message.answer("Asosiy menyu", reply_markup=main_menu_keyboard())


@router.message(F.text == MENU_TEST_CREATE_TEXT)
async def request_pdf_for_quiz_from_menu(message: Message, state: FSMContext):
    await state.set_state(QuizGenerationState.waiting_for_pdf)
    await message.answer("PDF fayl yuboring. Test shu fayldan yaratiladi.")


@router.message(F.text.in_({MENU_TESTS_TEXT, MENU_TEST_WORK_TEXT}))
async def show_quizzes_from_menu(message: Message, state: FSMContext):
    await state.set_state(None)
    await show_quiz_catalog(
        message,
        state,
        page=1,
        single_player=True,
    )


@router.message(F.text == MENU_FRIENDS_TEXT)
async def show_friends_quizzes_from_menu(message: Message, state: FSMContext):
    await state.set_state(None)
    await show_quiz_catalog(message, state, page=1, friends_mode=True)


@router.message(F.text == MENU_RESULTS_TEXT)
async def show_results_from_menu(message: Message, state: FSMContext):
    await state.set_state(None)
    await show_result_history(message, page=1)


@router.message(F.text.in_(MENU_TEXT_MESSAGES.keys()))
async def handle_menu_message(message: Message, state: FSMContext):
    await state.set_state(None)
    await message.answer(MENU_TEXT_MESSAGES[message.text])


@router.callback_query(F.data == MENU_TEST_CREATE)
async def request_pdf_for_quiz(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuizGenerationState.waiting_for_pdf)
    await callback.answer()
    await callback.message.answer("PDF fayl yuboring. Test shu fayldan yaratiladi.")


@router.callback_query(F.data.in_({MENU_TESTS, MENU_TEST_WORK}))
async def show_quizzes(callback: CallbackQuery, state: FSMContext):
    if callback.message is not None:
        await state.update_data(quiz_catalog_header_message_id=callback.message.message_id)
    await show_quiz_catalog(
        callback,
        state,
        page=1,
        single_player=True,
    )


@router.callback_query(F.data == MENU_FRIENDS)
async def show_friends_quizzes(callback: CallbackQuery, state: FSMContext):
    if callback.message is not None:
        await state.update_data(quiz_catalog_header_message_id=callback.message.message_id)
    await show_quiz_catalog(callback, state, page=1, friends_mode=True)


@router.callback_query(F.data == MENU_RESULTS)
async def show_results(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await show_result_history(callback, page=1)


@router.callback_query(F.data.startswith(RESULTS_LIST_PAGE))
async def paginate_results(callback: CallbackQuery):
    page_value = callback.data.removeprefix(RESULTS_LIST_PAGE) if callback.data else ""
    if not page_value.isdigit():
        await callback.answer("Sahifa raqami yaroqsiz.", show_alert=True)
        return
    await show_result_history(callback, page=int(page_value))


@router.callback_query(F.data == RESULTS_CURRENT)
async def show_current_results_page(callback: CallbackQuery):
    await callback.answer()


async def paginate_quiz_catalog(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    prefix: str,
    single_player: bool = False,
    friends_mode: bool = False,
) -> None:
    page_value = callback.data.removeprefix(prefix) if callback.data else ""
    if not page_value.isdigit():
        await callback.answer("Sahifa raqami yaroqsiz.", show_alert=True)
        return
    await show_quiz_catalog(
        callback,
        state,
        page=int(page_value),
        single_player=single_player,
        friends_mode=friends_mode,
    )


@router.callback_query(F.data.startswith(SINGLE_QUIZ_LIST_PAGE))
async def paginate_single_player_quizzes(callback: CallbackQuery, state: FSMContext):
    await paginate_quiz_catalog(
        callback,
        state,
        prefix=SINGLE_QUIZ_LIST_PAGE,
        single_player=True,
    )


@router.callback_query(F.data.startswith(FRIENDS_QUIZ_LIST_PAGE))
async def paginate_friends_quizzes(callback: CallbackQuery, state: FSMContext):
    await paginate_quiz_catalog(
        callback,
        state,
        prefix=FRIENDS_QUIZ_LIST_PAGE,
        friends_mode=True,
    )


@router.callback_query(F.data.in_({"single:quizzes:current", "friends:quizzes:current"}))
async def show_current_quiz_page(callback: CallbackQuery):
    await callback.answer()


async def show_duration_menu(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    prefix: str,
    single_player: bool = False,
    friends_mode: bool = False,
) -> None:
    values = parse_callback_values(callback.data, prefix, 2)
    if values is None or callback.message is None:
        await callback.answer("Test havolasi yaroqsiz.", show_alert=True)
        return
    quiz_id, page = values
    quiz = await get_telegram_user_quiz(callback.from_user.id, quiz_id)
    if quiz is None:
        await callback.answer("Test topilmadi yoki sizga tegishli emas.", show_alert=True)
        return
    await remove_catalog_messages(
        callback.bot,
        callback.message.chat.id,
        state,
        keep_message_id=callback.message.message_id,
        include_header=True,
    )
    await state.set_state(None)
    await callback.message.edit_text(
        "⏱ <b>Test vaqtini tanlang</b>",
        reply_markup=quiz_duration_keyboard(
            quiz_id,
            page,
            single_player=single_player,
            friends_mode=friends_mode,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith(SINGLE_QUIZ_DURATION_MENU))
async def select_single_player_duration(callback: CallbackQuery, state: FSMContext):
    await show_duration_menu(
        callback,
        state,
        prefix=SINGLE_QUIZ_DURATION_MENU,
        single_player=True,
    )


@router.callback_query(F.data.startswith(FRIENDS_QUIZ_DURATION_MENU))
async def select_friends_duration(callback: CallbackQuery, state: FSMContext):
    await show_duration_menu(
        callback,
        state,
        prefix=FRIENDS_QUIZ_DURATION_MENU,
        friends_mode=True,
    )


@router.callback_query(F.data.startswith(SINGLE_QUIZ_DURATION_SET))
async def set_single_player_duration(callback: CallbackQuery, state: FSMContext):
    values = parse_callback_values(callback.data, SINGLE_QUIZ_DURATION_SET, 3)
    if values is None or callback.message is None:
        await callback.answer("Vaqt qiymati yaroqsiz.", show_alert=True)
        return
    quiz_id, minutes, _ = values
    quiz = await get_telegram_user_quiz(callback.from_user.id, quiz_id)
    if quiz is None:
        await callback.answer("Test topilmadi yoki sizga tegishli emas.", show_alert=True)
        return
    try:
        minutes = parse_duration(minutes)
        await callback.message.edit_text(
            format_single_player_ready(quiz, minutes),
            reply_markup=quiz_webapp_keyboard(quiz_id, minutes),
            parse_mode="HTML",
        )
    except ValueError:
        await callback.answer("Telegram Mini App HTTPS manzili sozlanmagan.", show_alert=True)
        return
    except HTTPException as exc:
        await callback.answer(str(exc.detail), show_alert=True)
        return
    await state.set_state(None)
    await callback.answer("Test tayyor.")


@router.callback_query(F.data.startswith(FRIENDS_QUIZ_DURATION_SET))
async def set_friends_duration(callback: CallbackQuery, state: FSMContext):
    values = parse_callback_values(callback.data, FRIENDS_QUIZ_DURATION_SET, 3)
    if values is None or callback.message is None:
        await callback.answer("Vaqt qiymati yaroqsiz.", show_alert=True)
        return
    quiz_id, minutes, _ = values
    if await get_telegram_user_quiz(callback.from_user.id, quiz_id) is None:
        await callback.answer("Test topilmadi yoki sizga tegishli emas.", show_alert=True)
        return
    try:
        await create_room(
            callback.bot,
            callback.from_user.id,
            callback.message.chat.id,
            callback.message.message_id,
            quiz_id,
            parse_duration(minutes),
        )
    except HTTPException as exc:
        await callback.answer(str(exc.detail), show_alert=True)
        return
    await state.set_state(None)
    await callback.answer("Xona yaratildi.")


async def prepare_custom_duration(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    prefix: str,
    target_state,
    single_player: bool = False,
    friends_mode: bool = False,
) -> None:
    values = parse_callback_values(callback.data, prefix, 2)
    if values is None or callback.message is None:
        await callback.answer("Test havolasi yaroqsiz.", show_alert=True)
        return
    quiz_id, page = values
    if await get_telegram_user_quiz(callback.from_user.id, quiz_id) is None:
        await callback.answer("Test topilmadi yoki sizga tegishli emas.", show_alert=True)
        return
    await state.set_state(target_state)
    await state.update_data(
        duration_quiz_id=quiz_id,
        duration_page=page,
        duration_message_id=callback.message.message_id,
    )
    await callback.message.edit_text(
        "✏️ <b>Vaqtni kiriting</b>\nTest uchun vaqtni daqiqada yuboring. Masalan: <b>25</b>",
        reply_markup=quiz_custom_duration_keyboard(
            quiz_id,
            page,
            single_player=single_player,
            friends_mode=friends_mode,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith(SINGLE_QUIZ_DURATION_CUSTOM))
async def request_single_player_custom_duration(callback: CallbackQuery, state: FSMContext):
    await prepare_custom_duration(
        callback,
        state,
        prefix=SINGLE_QUIZ_DURATION_CUSTOM,
        target_state=QuizDurationState.waiting_for_single_player_custom_minutes,
        single_player=True,
    )


@router.callback_query(F.data.startswith(FRIENDS_QUIZ_DURATION_CUSTOM))
async def request_friends_custom_duration(callback: CallbackQuery, state: FSMContext):
    await prepare_custom_duration(
        callback,
        state,
        prefix=FRIENDS_QUIZ_DURATION_CUSTOM,
        target_state=QuizDurationState.waiting_for_friends_custom_minutes,
        friends_mode=True,
    )


async def return_to_quiz_catalog(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    prefix: str,
    single_player: bool = False,
    friends_mode: bool = False,
) -> None:
    values = parse_callback_values(callback.data, prefix, 2)
    if values is None:
        await callback.answer("Test havolasi yaroqsiz.", show_alert=True)
        return
    _, page = values
    await state.set_state(None)
    await show_quiz_catalog(
        callback,
        state,
        page=page,
        single_player=single_player,
        friends_mode=friends_mode,
    )


@router.callback_query(F.data.startswith(SINGLE_QUIZ_CARD))
async def return_to_single_player_quiz_card(callback: CallbackQuery, state: FSMContext):
    await return_to_quiz_catalog(
        callback,
        state,
        prefix=SINGLE_QUIZ_CARD,
        single_player=True,
    )


@router.callback_query(F.data.startswith(FRIENDS_QUIZ_CARD))
async def return_to_friends_quiz_card(callback: CallbackQuery, state: FSMContext):
    await return_to_quiz_catalog(
        callback,
        state,
        prefix=FRIENDS_QUIZ_CARD,
        friends_mode=True,
    )


async def custom_duration_values(message: Message, state: FSMContext):
    if message.from_user is None:
        await state.set_state(None)
        return None

    raw_minutes = (message.text or "").strip()
    try:
        minutes = parse_duration(raw_minutes)
    except HTTPException as exc:
        await message.answer(f"❗ {exc.detail}")
        return None

    data = await state.get_data()
    quiz_id = data.get("duration_quiz_id")
    message_id = data.get("duration_message_id")
    if not isinstance(quiz_id, int) or not isinstance(message_id, int):
        await state.set_state(None)
        await message.answer("Vaqt tanlash oynasi muddati tugagan. Testlar ro'yxatidan qayta boshlang.")
        return None

    quiz = await get_telegram_user_quiz(message.from_user.id, quiz_id)
    if quiz is None:
        await state.set_state(None)
        await message.answer("Test topilmadi yoki sizga tegishli emas.")
        return None

    return quiz, message_id, minutes


@router.message(QuizDurationState.waiting_for_single_player_custom_minutes)
async def receive_single_player_custom_duration(message: Message, state: FSMContext):
    values = await custom_duration_values(message, state)
    if values is None:
        return
    quiz, message_id, minutes = values
    quiz_id = quiz["id"]

    try:
        await message.bot.edit_message_text(
            format_single_player_ready(quiz, minutes),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=quiz_webapp_keyboard(quiz_id, minutes),
            parse_mode="HTML",
        )
    except ValueError:
        await message.answer("❗ Telegram Mini App HTTPS manzili sozlanmagan.")
        return
    except HTTPException as exc:
        await message.answer(f"❗ {exc.detail}")
        return
    await state.set_state(None)
    await message.answer("Test tayyor.")


@router.message(QuizDurationState.waiting_for_friends_custom_minutes)
async def receive_friends_custom_duration(message: Message, state: FSMContext):
    values = await custom_duration_values(message, state)
    if values is None:
        return
    quiz, message_id, minutes = values
    quiz_id = quiz["id"]

    try:
        await create_room(
            message.bot,
            message.from_user.id,
            message.chat.id,
            message_id,
            quiz_id,
            minutes,
        )
    except HTTPException as exc:
        await message.answer(f"❗ {exc.detail}")
        return
    await state.set_state(None)
    await message.answer("Xona yaratildi.")


@router.callback_query(F.data.in_(MENU_MESSAGES.keys()))
async def handle_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(MENU_MESSAGES[callback.data])
