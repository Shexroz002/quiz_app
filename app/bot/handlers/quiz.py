from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fastapi import HTTPException

from app.bot.keyboards.inline import (
    AI_CANCEL,
    AI_COUNT_CUSTOM,
    AI_COUNT_SET,
    AI_MAX_QUESTIONS,
    AI_MIN_QUESTIONS,
    AI_SUBJECT_PAGE,
    AI_SUBJECT_PAGE_SIZE,
    AI_SUBJECT_PICK,
    MENU_TEST_CREATE_AI,
    MENU_TEST_CREATE_PDF,
    QUIZ_OPEN,
    QUIZ_REVIEW,
    QUIZ_START,
    ai_question_count_keyboard,
    ai_subject_keyboard,
    quiz_review_webapp_keyboard,
    quiz_webapp_keyboard,
)
from app.bot.handlers.menu import subject_icon
from app.bot.states import QuizGenerationState
from app.bot.utils.progress import (
    edit_progress_message,
    format_ai_received_text,
    format_failed_text,
    format_received_text,
    save_job_message_mapping,
    start_progress_watcher,
)
from app.bot.utils.registration import get_user_by_telegram_id
from app.bot.utils.upload import TelegramUploadFile
from app.core.config import settings
from app.core.database.base import AsyncSessionLocal
from app.core.database.redis import get_redis_client
from app.repositories.quiz.quiz_repo import QuizRepository
from app.services.pdf.pdf_job_service import PDFJobService
from app.services.pdf.storage_service import StorageService
from app.services.subject.subject_service import SubjectService

router = Router()


async def user_owns_quiz(telegram_id: int, quiz_id: int) -> bool:
    user = await get_user_by_telegram_id(telegram_id)
    if user is None or not user.is_active:
        return False
    async with AsyncSessionLocal() as db:
        return await QuizRepository(db).get(quiz_id, user.id) is not None


MAX_DESCRIPTION_LENGTH = 1000


def _pdf_job_service(db):
    return PDFJobService(
        db=db,
        storage=StorageService(
            upload_dir=settings.UPLOAD_DIR,
            max_size_bytes=settings.MAX_PDF_SIZE,
        ),
    )


async def _watch_job(bot, chat_id: int, status_message, job) -> None:
    """Bind the status message to the job and start streaming its progress."""
    redis_client = get_redis_client()
    mapping = {
        "job_id": str(job.id),
        "telegram_chat_id": chat_id,
        "telegram_message_id": status_message.message_id,
    }
    await save_job_message_mapping(
        redis_client=redis_client,
        job_id=str(job.id),
        telegram_chat_id=chat_id,
        telegram_message_id=status_message.message_id,
    )
    await edit_progress_message(
        bot,
        mapping,
        {
            "status": job.status.value,
            "progress": job.progress,
            "message": job.message,
            "job_id": str(job.id),
            "file_name": job.file_name,
            "description": job.description,
            "number_questions": job.number_questions,
        },
    )
    start_progress_watcher(bot, str(job.id))


async def load_subjects_page(page: int):
    async with AsyncSessionLocal() as db:
        subjects = await SubjectService(db).list()
    rows = [
        {"id": subject.id, "name": subject.name, "icon": subject.icon or subject_icon(subject.name)}
        for subject in subjects
    ]
    total_pages = max(1, -(-len(rows) // AI_SUBJECT_PAGE_SIZE))
    page = min(max(page, 1), total_pages)
    start = (page - 1) * AI_SUBJECT_PAGE_SIZE
    return rows[start:start + AI_SUBJECT_PAGE_SIZE], page, total_pages, len(rows)


@router.callback_query(F.data == MENU_TEST_CREATE_PDF)
async def choose_pdf_source(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuizGenerationState.waiting_for_pdf)
    await callback.answer()
    await callback.message.answer("PDF fayl yuboring. Test shu fayldan yaratiladi.")


@router.callback_query(F.data == MENU_TEST_CREATE_AI)
async def choose_ai_source(callback: CallbackQuery, state: FSMContext):
    subjects, page, total_pages, total = await load_subjects_page(1)
    if not total:
        await callback.answer("Fanlar ro‘yxati bo‘sh. Administratorga murojaat qiling.", show_alert=True)
        return
    await state.set_state(QuizGenerationState.waiting_for_ai_subject)
    await callback.answer()
    await callback.message.answer(
        "Qaysi fandan test yarataylik?",
        reply_markup=ai_subject_keyboard(subjects, page, total_pages),
    )


@router.callback_query(F.data.startswith(AI_SUBJECT_PAGE))
async def paginate_ai_subjects(callback: CallbackQuery):
    raw_page = callback.data.rsplit(":", 1)[-1]
    subjects, page, total_pages, _ = await load_subjects_page(
        int(raw_page) if raw_page.isdigit() else 1
    )
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(
            reply_markup=ai_subject_keyboard(subjects, page, total_pages)
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(F.data.startswith(AI_SUBJECT_PICK))
async def pick_ai_subject(callback: CallbackQuery, state: FSMContext):
    subject_id = callback.data.rsplit(":", 1)[-1]
    if not subject_id.isdigit():
        await callback.answer("Fan tanlanmadi.", show_alert=True)
        return

    async with AsyncSessionLocal() as db:
        subjects = await SubjectService(db).list()
    subject = next((item for item in subjects if item.id == int(subject_id)), None)
    if subject is None:
        await callback.answer("Bu fan topilmadi.", show_alert=True)
        return

    await state.update_data(ai_subject_id=subject.id, ai_subject_name=subject.name)
    await state.set_state(QuizGenerationState.waiting_for_ai_description)
    await callback.answer()
    await callback.message.answer(
        f"Fan: <b>{subject.name}</b>\n\n"
        "Endi mavzuni yozing. Qanchalik aniq yozsangiz, test shunchalik mos bo‘ladi.\n\n"
        "Masalan: <i>9-sinf, aritmetik progressiya: hadni va yig‘indini topish</i>",
        parse_mode="HTML",
    )


@router.message(QuizGenerationState.waiting_for_ai_description, F.text)
async def receive_ai_description(message: Message, state: FSMContext):
    description = (message.text or "").strip()
    if len(description) < 3:
        await message.answer("Mavzu juda qisqa. Biroz batafsilroq yozing.")
        return
    if len(description) > MAX_DESCRIPTION_LENGTH:
        await message.answer(
            f"Mavzu juda uzun ({len(description)} belgi). "
            f"{MAX_DESCRIPTION_LENGTH} belgidan oshmasin."
        )
        return

    await state.update_data(ai_description=description)
    await state.set_state(QuizGenerationState.waiting_for_ai_question_count)
    await message.answer(
        "Nechta savol bo‘lsin?",
        reply_markup=ai_question_count_keyboard(),
    )


@router.message(QuizGenerationState.waiting_for_ai_description)
async def reject_non_text_description(message: Message):
    await message.answer("Mavzuni matn ko‘rinishida yozing.")


async def _create_ai_quiz_job(message: Message, state: FSMContext, bot: Bot, count: int):
    telegram_user = message.chat
    user = await get_user_by_telegram_id(telegram_user.id)
    if not user:
        await state.clear()
        await message.answer("Avval /start orqali ro‘yxatdan o‘ting.")
        return

    data = await state.get_data()
    subject_id = data.get("ai_subject_id")
    description = data.get("ai_description")
    if not subject_id or not description:
        await state.clear()
        await message.answer("Ma’lumot yo‘qoldi. «➕ Test yaratish» dan qaytadan boshlang.")
        return

    status_message = await message.answer(format_ai_received_text(description, count))
    try:
        async with AsyncSessionLocal() as db:
            job = await _pdf_job_service(db).create_job_by_description(
                subject=subject_id,
                description=description,
                question_count=count,
                user_id=user.id,
            )
        await _watch_job(bot, message.chat.id, status_message, job)
        await state.clear()
    except HTTPException as exc:
        await state.clear()
        await status_message.edit_text(format_failed_text(str(exc.detail), ai=True))
    except Exception:
        await state.clear()
        await status_message.edit_text(format_failed_text(ai=True))


@router.callback_query(
    QuizGenerationState.waiting_for_ai_question_count,
    F.data.startswith(AI_COUNT_SET),
)
async def set_ai_question_count(callback: CallbackQuery, state: FSMContext, bot: Bot):
    raw_count = callback.data.rsplit(":", 1)[-1]
    if not raw_count.isdigit():
        await callback.answer("Savollar soni noto‘g‘ri.", show_alert=True)
        return
    await callback.answer()
    await _create_ai_quiz_job(callback.message, state, bot, int(raw_count))


@router.callback_query(
    QuizGenerationState.waiting_for_ai_question_count,
    F.data == AI_COUNT_CUSTOM,
)
async def request_custom_question_count(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        f"Savollar sonini yozing ({AI_MIN_QUESTIONS}–{AI_MAX_QUESTIONS})."
    )


@router.message(QuizGenerationState.waiting_for_ai_question_count, F.text)
async def receive_custom_question_count(message: Message, state: FSMContext, bot: Bot):
    raw_count = (message.text or "").strip()
    if not raw_count.isdigit():
        await message.answer(f"Faqat son yozing ({AI_MIN_QUESTIONS}–{AI_MAX_QUESTIONS}).")
        return
    count = int(raw_count)
    if not AI_MIN_QUESTIONS <= count <= AI_MAX_QUESTIONS:
        await message.answer(
            f"Savollar soni {AI_MIN_QUESTIONS} bilan {AI_MAX_QUESTIONS} orasida bo‘lsin."
        )
        return
    await _create_ai_quiz_job(message, state, bot, count)


@router.callback_query(F.data == AI_CANCEL)
async def cancel_ai_generation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Bekor qilindi.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


@router.message(QuizGenerationState.waiting_for_pdf, F.document)
async def receive_pdf_for_quiz(message: Message, state: FSMContext, bot: Bot):
    telegram_user = message.from_user
    document = message.document
    if telegram_user is None or document is None:
        return

    user = await get_user_by_telegram_id(telegram_user.id)
    if not user:
        await state.clear()
        await message.answer("Avval /start orqali ro'yxatdan o'ting.")
        return

    filename = document.file_name or "telegram_quiz.pdf"
    status_message = await message.answer(format_received_text(filename))

    buffer = await bot.download(document.file_id, destination=BytesIO())
    if buffer is None:
        await status_message.edit_text(
            format_failed_text("PDF faylni Telegramdan yuklab bo‘lmadi.")
        )
        return

    upload_file = TelegramUploadFile(
        data=buffer.getvalue(),
        filename=filename,
        content_type=document.mime_type,
    )

    try:
        async with AsyncSessionLocal() as db:
            job = await _pdf_job_service(db).create_job_and_queue(
                file=upload_file,
                user_id=user.id,
            )
        await _watch_job(bot, message.chat.id, status_message, job)
        await state.clear()
    except HTTPException as exc:
        await status_message.edit_text(format_failed_text(str(exc.detail)))
    except Exception:
        await status_message.edit_text(format_failed_text())


@router.message(QuizGenerationState.waiting_for_pdf)
async def reject_non_pdf(message: Message):
    await message.answer("Iltimos, PDF fayl yuboring.")


@router.callback_query(F.data.startswith(f"{QUIZ_OPEN}:"))
async def open_generated_quiz(callback: CallbackQuery):
    quiz_id = callback.data.rsplit(":", 1)[-1] if callback.data else ""
    if not quiz_id.isdigit() or callback.message is None:
        await callback.answer("Test havolasi yaroqsiz.", show_alert=True)
        return

    quiz_id = int(quiz_id)
    if not await user_owns_quiz(callback.from_user.id, quiz_id):
        await callback.answer("Test topilmadi yoki sizga tegishli emas.", show_alert=True)
        return

    try:
        reply_markup = quiz_webapp_keyboard(quiz_id)
    except ValueError:
        await callback.answer("HTTPS tunnel hali tayyor emas. Birozdan so'ng qayta urining.", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer("Testni ochish uchun tugmani bosing.", reply_markup=reply_markup)


@router.callback_query(F.data.startswith(f"{QUIZ_REVIEW}:"))
async def review_generated_quiz(callback: CallbackQuery):
    quiz_id = callback.data.rsplit(":", 1)[-1] if callback.data else ""
    if not quiz_id.isdigit() or callback.message is None:
        await callback.answer("Test havolasi yaroqsiz.", show_alert=True)
        return

    quiz_id = int(quiz_id)
    if not await user_owns_quiz(callback.from_user.id, quiz_id):
        await callback.answer("Test topilmadi yoki sizga tegishli emas.", show_alert=True)
        return

    try:
        reply_markup = quiz_review_webapp_keyboard(quiz_id)
    except ValueError:
        await callback.answer("HTTPS tunnel hali tayyor emas. Birozdan so'ng qayta urining.", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(
        "Savollarni tekshirish uchun tugmani bosing.",
        reply_markup=reply_markup,
    )


@router.callback_query(F.data.startswith(f"{QUIZ_START}:"))
async def start_generated_quiz(callback: CallbackQuery):
    quiz_id = callback.data.rsplit(":", 1)[-1] if callback.data else ""
    if not quiz_id.isdigit() or callback.message is None:
        await callback.answer("Test havolasi yaroqsiz.", show_alert=True)
        return
    if not await user_owns_quiz(callback.from_user.id, int(quiz_id)):
        await callback.answer("Test topilmadi yoki sizga tegishli emas.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(f"Testni boshlash: {quiz_id}")
