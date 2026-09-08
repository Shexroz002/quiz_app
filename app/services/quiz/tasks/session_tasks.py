import asyncio
import logging

from redis.asyncio import Redis

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database.base import CeleryAsyncSessionLocal
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository
from app.services.quiz.quiz_session import QuizSessionService
from app.utils.datetime import utc_now


logger = logging.getLogger(__name__)


async def _finalize(session_id: int, reason: str) -> None:
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        async with CeleryAsyncSessionLocal() as db:
            await QuizSessionService(db, redis).finalize_session(session_id, reason)
    finally:
        await redis.aclose()


@celery_app.task(
    bind=True,
    name="quiz.finalize_session",
    queue="quiz_session",
    max_retries=5,
    default_retry_delay=10,
)
def finalize_quiz_session(self, session_id: int, reason: str = "time_expired") -> None:
    try:
        asyncio.run(_finalize(session_id, reason))
    except Exception as exc:
        logger.exception("Quiz session %s finalization failed", session_id)
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="quiz.finalize_expired_sessions",
    queue="quiz_session",
    max_retries=3,
    default_retry_delay=10,
)
def finalize_expired_quiz_sessions(self) -> None:
    async def runner() -> None:
        async with CeleryAsyncSessionLocal() as db:
            session_ids = await QuizSessionRepository(db).get_expired_running_session_ids(utc_now())
        for session_id in session_ids:
            await _finalize(session_id, "time_expired")

    try:
        asyncio.run(runner())
    except Exception as exc:
        logger.exception("Expired quiz session recovery failed")
        raise self.retry(exc=exc)
