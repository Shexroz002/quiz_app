"""Durable private-chat delivery for finished single-player quiz results."""

import logging
from html import escape

from fastapi import HTTPException
from sqlalchemy import select

from app.bot.models import TelegramSinglePlayerResultDelivery
from app.core.database.base import AsyncSessionLocal
from app.models.quiz.real_time_quiz.quiz_session import SessionType
from app.services.quiz.quiz_session import QuizSessionService
from app.utils.datetime import utc_now


logger = logging.getLogger(__name__)


def queue_single_player_result_delivery(delivery_id: int) -> None:
    try:
        from app.core.celery_app import celery_app

        celery_app.send_task(
            "telegram.deliver_single_player_result",
            args=[delivery_id],
            queue="telegram_quiz",
        )
    except Exception:
        logger.exception("Could not queue Telegram result delivery %s", delivery_id)


async def request_single_player_result_delivery(db, session_id: int, user):
    service = QuizSessionService(db)
    session = await service.session_repo.get_by_id_for_update(session_id)
    if session is None:
        raise HTTPException(404, "Test sessiyasi topilmadi.")
    if session.session_type != SessionType.individual:
        raise HTTPException(400, "Bu yakka tartibdagi test emas.")

    participant = await service.participant_repo.get_by_session_user(session_id, user.id)
    if participant is None:
        raise HTTPException(403, "Siz bu test ishtirokchisi emassiz.")
    attempt = await service.attempt_repo.get_by_session_participant(session_id, participant.id)
    if attempt is None or not attempt.finished:
        raise HTTPException(409, "Avval testni yakunlang.")
    if not user.telegram_id:
        raise HTTPException(409, "Telegram profilingiz foydalanuvchiga bog'lanmagan.")
    try:
        chat_id = int(user.telegram_id)
    except (TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(409, "Telegram chat identifikatori yaroqsiz.") from exc

    delivery = (
        await db.execute(
            select(TelegramSinglePlayerResultDelivery).where(
                TelegramSinglePlayerResultDelivery.attempt_id == attempt.id
            )
        )
    ).scalar_one_or_none()
    if delivery is None:
        delivery = TelegramSinglePlayerResultDelivery(
            attempt_id=attempt.id,
            session_id=session_id,
            user_id=user.id,
            chat_id=chat_id,
        )
        db.add(delivery)
        await db.flush()

    await db.commit()
    if delivery.delivered_at is None:
        queue_single_player_result_delivery(delivery.id)
    return delivery


def format_single_player_result(result: dict) -> str:
    total = result["total_questions"]
    answered = result["answered_questions"]
    correct = result["correct_answers"]
    seconds_total = result["spend_time"]
    minutes, seconds = divmod(seconds_total, 60)
    lines = [
        "✅ <b>Test yakunlandi!</b>",
        f"📚 <b>{escape(result['quiz_title'][:180])}</b>",
    ]
    if result.get("subject"):
        lines.append(f"📖 {escape(result['subject'][:80])}")
    lines.extend(
        [
            f"🎯 To'g'ri javoblar: <b>{correct}/{total}</b>",
            f"📝 Javob berilgan: <b>{answered}/{total}</b>",
            f"📊 Natija: <b>{result['percentage']:g}%</b>",
            f"⏱ Sarflangan vaqt: <b>{minutes:02}:{seconds:02}</b>",
        ]
    )
    return "\n".join(lines)


async def deliver_single_player_result(bot, delivery_id: int, session_factory=AsyncSessionLocal) -> None:
    async with session_factory() as db:
        delivery = (
            await db.execute(
                select(TelegramSinglePlayerResultDelivery)
                .where(TelegramSinglePlayerResultDelivery.id == delivery_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if delivery is None or delivery.delivered_at is not None:
            return

        result = await QuizSessionService(db).get_finished_single_player_result(
            delivery.session_id,
            delivery.user_id,
        )
        await bot.send_message(
            chat_id=delivery.chat_id,
            text=format_single_player_result(result),
            parse_mode="HTML",
        )
        delivery.delivered_at = utc_now()
        await db.commit()
