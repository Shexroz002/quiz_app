from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fastapi import HTTPException

from app.bot.keyboards.inline import QUIZ_OPEN, QUIZ_START, quiz_webapp_keyboard
from app.bot.states import QuizGenerationState
from app.bot.utils.progress import (
    edit_progress_message,
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

router = Router()


async def user_owns_quiz(telegram_id: int, quiz_id: int) -> bool:
    user = await get_user_by_telegram_id(telegram_id)
    if user is None or not user.is_active:
        return False
    async with AsyncSessionLocal() as db:
        return await QuizRepository(db).get(quiz_id, user.id) is not None


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
            storage = StorageService(
                upload_dir=settings.UPLOAD_DIR,
                max_size_bytes=settings.MAX_PDF_SIZE,
            )
            service = PDFJobService(db=db, storage=storage)
            job = await service.create_job_and_queue(file=upload_file, user_id=user.id)

        redis_client = get_redis_client()
        await save_job_message_mapping(
            redis_client=redis_client,
            job_id=str(job.id),
            telegram_chat_id=message.chat.id,
            telegram_message_id=status_message.message_id,
        )
        await edit_progress_message(
            bot,
            {
                "job_id": str(job.id),
                "telegram_chat_id": message.chat.id,
                "telegram_message_id": status_message.message_id,
            },
            {
                "status": "queued",
                "progress": job.progress,
                "message": job.message,
                "job_id": str(job.id),
                "file_name": job.file_name,
            },
        )
        start_progress_watcher(bot, str(job.id))
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
