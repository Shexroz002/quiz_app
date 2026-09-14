"""Durable private-chat delivery of a per-participant analysis for finished rooms.

The group message keeps carrying the shared leaderboard; this is the personal
breakdown each participant gets in their own chat with the bot.
"""

import logging
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound
from sqlalchemy import and_, select

from app.bot.models import TelegramRoomAnalysisDelivery
from app.bot.services.analysis_message import analysis_keyboard, format_analysis_message
from app.core.database.base import AsyncSessionLocal
from app.models import QuizSession, User
from app.models.quiz.real_time_quiz.quiz_attempt import QuizAttempt
from app.models.quiz.real_time_quiz.session_participant import SessionParticipant
from app.services.quiz.multiplayer import MultiplayerQuizService
from app.utils.datetime import utc_now


logger = logging.getLogger(__name__)


def queue_room_analysis_deliveries(delivery_ids) -> None:
    if not delivery_ids:
        return
    try:
        from app.core.celery_app import celery_app

        for delivery_id in delivery_ids:
            celery_app.send_task(
                "telegram.deliver_room_analysis",
                args=[delivery_id],
                queue="telegram_quiz",
            )
    except Exception:
        logger.exception("Could not queue Telegram room analysis for %s", delivery_ids)


async def create_room_analysis_deliveries(db, session_id: int) -> list[int]:
    """Add one outbox row per finished participant. Idempotent; caller commits."""
    rows = (
        await db.execute(
            select(
                QuizAttempt.id.label("attempt_id"),
                SessionParticipant.user_id.label("user_id"),
                User.telegram_id.label("telegram_id"),
            )
            .select_from(SessionParticipant)
            .join(User, User.id == SessionParticipant.user_id)
            .join(
                QuizAttempt,
                and_(
                    QuizAttempt.session_id == SessionParticipant.session_id,
                    QuizAttempt.participant_id == SessionParticipant.id,
                ),
            )
            .where(
                SessionParticipant.session_id == session_id,
                QuizAttempt.finished.is_(True),
            )
        )
    ).mappings().all()

    existing = set(
        (
            await db.execute(
                select(TelegramRoomAnalysisDelivery.attempt_id).where(
                    TelegramRoomAnalysisDelivery.session_id == session_id
                )
            )
        ).scalars().all()
    )

    deliveries = []
    for row in rows:
        if row["attempt_id"] in existing:
            continue
        try:
            chat_id = int(row["telegram_id"])
        except (TypeError, ValueError, OverflowError):
            continue
        delivery = TelegramRoomAnalysisDelivery(
            attempt_id=row["attempt_id"],
            session_id=session_id,
            user_id=row["user_id"],
            chat_id=chat_id,
        )
        db.add(delivery)
        deliveries.append(delivery)

    if not deliveries:
        return []
    await db.flush()
    return [delivery.id for delivery in deliveries]


async def deliver_room_analysis(bot, delivery_id: int, session_factory=AsyncSessionLocal) -> None:
    async with session_factory() as db:
        delivery = (
            await db.execute(
                select(TelegramRoomAnalysisDelivery)
                .where(TelegramRoomAnalysisDelivery.id == delivery_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if delivery is None or delivery.delivered_at is not None:
            return

        service = MultiplayerQuizService(db)
        session = await db.get(QuizSession, delivery.session_id)
        if session is None:
            return
        result = await service.get_finished_attempt_result(
            delivery.session_id,
            delivery.user_id,
        )
        leaderboard = await service.leaderboard(session)
        try:
            await bot.send_message(
                chat_id=delivery.chat_id,
                text=format_analysis_message(result, leaderboard, delivery.user_id),
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=analysis_keyboard(delivery.session_id),
            )
        except (TelegramForbiddenError, TelegramNotFound):
            # Blocked the bot, or never opened a private chat. Retrying can never
            # succeed, and the recovery scan would re-queue this row every minute.
            logger.warning(
                "Telegram room analysis %s is undeliverable to chat %s",
                delivery_id,
                delivery.chat_id,
            )
        delivery.delivered_at = utc_now()
        await db.commit()
