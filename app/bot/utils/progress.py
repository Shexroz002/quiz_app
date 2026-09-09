import asyncio
import json

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from app.bot.keyboards.inline import generated_quiz_keyboard
from app.core.database.base import AsyncSessionLocal
from app.core.database.redis import get_redis_client
from app.models.quiz import Quiz
from app.models.quiz.ai_quiz.pdf_to_quiz import PDFJob

JOB_MAPPING_TTL_SECONDS = 60 * 60 * 24

def _mapping_key(job_id: str) -> str:
    return f"telegram_pdf_job:{job_id}"


async def save_job_message_mapping(
    *,
    redis_client,
    job_id: str,
    telegram_chat_id: int,
    telegram_message_id: int,
) -> None:
    await redis_client.hset(
        _mapping_key(job_id),
        mapping={
            "job_id": job_id,
            "telegram_chat_id": str(telegram_chat_id),
            "telegram_message_id": str(telegram_message_id),
        },
    )
    await redis_client.expire(_mapping_key(job_id), JOB_MAPPING_TTL_SECONDS)


async def get_job_message_mapping(redis_client, job_id: str) -> dict[str, int | str] | None:
    data = await redis_client.hgetall(_mapping_key(job_id))
    if not data:
        return None

    return {
        "job_id": data["job_id"],
        "telegram_chat_id": int(data["telegram_chat_id"]),
        "telegram_message_id": int(data["telegram_message_id"]),
    }


async def delete_job_message_mapping(redis_client, job_id: str) -> None:
    await redis_client.delete(_mapping_key(job_id))


def _progress_status(data: dict) -> str:
    status = data.get("status")
    status = getattr(status, "value", status)
    progress = int(data.get("progress") or 0)

    if status == "completed":
        return "COMPLETED"
    if status == "failed":
        return "FAILED"
    if progress >= 85:
        return "SAVING"
    if progress >= 20:
        return "QUESTIONS_GENERATING"
    if progress >= 10:
        return "AI_PREPARING"
    return "REQUEST_RECEIVED"


def progress_bar(progress: int, width: int = 10) -> str:
    bounded_progress = min(100, max(0, progress))
    filled = bounded_progress * width // 100
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def format_received_text(filename: str | None) -> str:
    return (
        "📄 Test yaratilmoqda\n\n"
        f"📎 {filename or 'PDF fayl'}\n"
        "✅ Fayl muvaffaqiyatli qabul qilindi\n\n"
        "⏳ Jarayon boshlandi..."
    )


def _safe_user_error(data: dict) -> str | None:
    error = str(data.get("error") or "").strip()
    if not error or len(error) > 300 or "\n" in error:
        return None
    technical_markers = (
        "traceback",
        "exception",
        "stack trace",
        "sqlalchemy",
        "redis",
        "celery",
        "/app/",
        "status code",
        "internal server error",
    )
    if any(marker in error.lower() for marker in technical_markers):
        return None
    return error


def format_failed_text(error: str | None = None) -> str:
    lines = [
        "😕 Testni yaratib bo‘lmadi",
        "",
        "PDF faylni qayta ishlashda muammo yuz berdi.",
    ]
    if error:
        lines.extend(["", error])
    lines.extend(
        [
            "",
            "Faylni tekshirib, yana bir marta urinib ko‘ring.",
        ]
    )
    return "\n".join(lines)


def format_progress_text(data: dict) -> str:
    status = _progress_status(data)
    progress = int(data.get("progress") or 0)
    filename = data.get("file_name") or "PDF fayl"
    bar = progress_bar(progress)

    if status == "COMPLETED":
        question_count = data.get("question_count") or 0
        subject = data.get("subject") or "Fan ko‘rsatilmagan"
        quiz_title = data.get("quiz_title") or "Yangi test"
        return (
            "🎉 Test tayyor!\n\n"
            f"📚 {subject}\n"
            f"📝 {quiz_title}\n\n"
            f"❓ {question_count} ta savol yaratildi\n"
            "✅ Test muvaffaqiyatli saqlandi\n\n"
            "Endi testni o‘zingiz ishlashingiz yoki do‘stlaringiz bilan "
            "boshlashingiz mumkin. 🚀"
        )
    if status == "FAILED":
        return format_failed_text(_safe_user_error(data))
    if status == "AI_PREPARING":
        return (
            "🔍 PDF tahlil qilinmoqda\n\n"
            f"📎 {filename}\n\n"
            "AI fayldagi savollar, rasmlar va formulalarni aniqlamoqda.\n\n"
            f"{bar} {progress}%\n\n"
            "⏳ Biroz kuting..."
        )
    if status == "QUESTIONS_GENERATING":
        return (
            "🧠 Savollar tayyorlanmoqda\n\n"
            f"📎 {filename}\n\n"
            "PDF tahlil qilindi ✅\n"
            "Hozir savollar va javob variantlari yaratilmoqda.\n\n"
            f"{bar} {progress}%\n\n"
            "✨ Test deyarli tayyor..."
        )
    if status == "SAVING":
        return (
            "💾 Test saqlanmoqda\n\n"
            "Savollar muvaffaqiyatli yaratildi ✅\n"
            "Test yakuniy ko‘rinishga tayyorlanmoqda.\n\n"
            f"{bar} {progress}%\n\n"
            "⏳ Yana bir oz..."
        )

    return format_received_text(data.get("file_name"))


async def get_pdf_job_snapshot(job_id: str) -> dict | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                PDFJob.status,
                PDFJob.progress,
                PDFJob.message,
                PDFJob.quiz_id,
                PDFJob.question_count,
                PDFJob.error,
                PDFJob.file_name,
                Quiz.title.label("quiz_title"),
                Quiz.subject,
            )
            .outerjoin(Quiz, Quiz.id == PDFJob.quiz_id)
            .where(PDFJob.id == job_id)
        )
        job = result.mappings().one_or_none()
        if job is None:
            return None

        return {
            "type": "snapshot",
            "job_id": job_id,
            "status": job["status"].value,
            "progress": job["progress"],
            "message": job["message"],
            "quiz_id": job["quiz_id"],
            "question_count": job["question_count"],
            "error": job["error"],
            "file_name": job["file_name"],
            "quiz_title": job["quiz_title"],
            "subject": job["subject"],
        }


async def edit_progress_message(bot: Bot, mapping: dict[str, int | str], data: dict) -> None:
    status = _progress_status(data)
    reply_markup = None
    if status == "COMPLETED" and data.get("quiz_id"):
        reply_markup = generated_quiz_keyboard(int(data["quiz_id"]))

    try:
        await bot.edit_message_text(
            chat_id=int(mapping["telegram_chat_id"]),
            message_id=int(mapping["telegram_message_id"]),
            text=format_progress_text(data),
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def watch_pdf_job_progress(bot: Bot, job_id: str) -> None:
    redis_client = get_redis_client()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"pdf_job:{job_id}")

    try:
        mapping = await get_job_message_mapping(redis_client, job_id)
        snapshot = await get_pdf_job_snapshot(job_id)
        if mapping and snapshot:
            await edit_progress_message(bot, mapping, snapshot)
            if snapshot.get("status") in ("completed", "failed"):
                await delete_job_message_mapping(redis_client, job_id)
                return

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            data = json.loads(message["data"])
            mapping = await get_job_message_mapping(redis_client, job_id)
            if mapping:
                snapshot = await get_pdf_job_snapshot(job_id)
                presentation_data = {**(snapshot or {}), **data}
                await edit_progress_message(bot, mapping, presentation_data)

            if data.get("status") in ("completed", "failed"):
                await delete_job_message_mapping(redis_client, job_id)
                break
    finally:
        await pubsub.unsubscribe(f"pdf_job:{job_id}")
        await pubsub.close()


def start_progress_watcher(bot: Bot, job_id: str) -> None:
    asyncio.create_task(watch_pdf_job_progress(bot, job_id))
