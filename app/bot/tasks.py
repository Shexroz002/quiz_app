import asyncio
import logging

from aiogram import Bot
from sqlalchemy import or_, select

from app.bot.models import TelegramQuizRoom, TelegramSinglePlayerResultDelivery
from app.bot.services.quiz_room import publish_room
from app.bot.services.single_player_result import deliver_single_player_result
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database.base import CeleryAsyncSessionLocal
from app.models import QuizSession
from app.services.quiz.multiplayer import MultiplayerQuizService

logger = logging.getLogger(__name__)


@celery_app.task(name="telegram.recover_rooms", queue="telegram_quiz")
def recover_rooms():
    asyncio.run(_recover_rooms())


async def _recover_rooms():
    async with CeleryAsyncSessionLocal() as db:
        ids = (await db.execute(select(TelegramQuizRoom.session_id).join(
            QuizSession, QuizSession.id == TelegramQuizRoom.session_id
        ).where(or_(
            QuizSession.status != "finished",
            TelegramQuizRoom.leaderboard_delivered_at.is_(None),
        )))).scalars().all()
        delivery_ids = (await db.execute(
            select(TelegramSinglePlayerResultDelivery.id).where(
                TelegramSinglePlayerResultDelivery.delivered_at.is_(None)
            )
        )).scalars().all()
    for session_id in ids:
        maintain_room.delay(session_id)
    for delivery_id in delivery_ids:
        deliver_result.delay(delivery_id)


@celery_app.task(name="telegram.maintain_room", autoretry_for=(Exception,),
                 retry_backoff=True, retry_backoff_max=60, max_retries=5,
                 queue="telegram_quiz")
def maintain_room(session_id):
    asyncio.run(_maintain_room(session_id))


async def _maintain_room(session_id):
    async with CeleryAsyncSessionLocal() as db:
        await MultiplayerQuizService(db).finalize_quiz_session(session_id)
    async with Bot(settings.TELEGRAM_BOT_TOKEN) as bot:
        await publish_room(bot, session_id, session_factory=CeleryAsyncSessionLocal)


@celery_app.task(
    name="telegram.deliver_single_player_result",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=5,
    queue="telegram_quiz",
)
def deliver_result(delivery_id):
    asyncio.run(_deliver_result(delivery_id))


async def _deliver_result(delivery_id):
    async with Bot(settings.TELEGRAM_BOT_TOKEN) as bot:
        await deliver_single_player_result(
            bot,
            delivery_id,
            session_factory=CeleryAsyncSessionLocal,
        )
