import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database.base import CeleryAsyncSessionLocal
from app.models import MistakeReview, Notification, NotificationActionType, NotificationType
from app.repositories.quiz.mistake_repo import MistakeRepository
from app.schemas.notification.notification import NotificationCreateSchema
from app.services.notification.notification_service import NotificationService
from app.utils.datetime import utc_now

logger = logging.getLogger(__name__)


async def _already_reminded_today(db, user_id: int, since) -> bool:
    """One reminder a day, so the bank never nags."""
    stmt = select(Notification.id).where(
        Notification.recipient_id == user_id,
        Notification.type == NotificationType.TEST_REMINDER,
        Notification.created_at >= since,
    )
    result = await db.execute(stmt)
    return result.first() is not None


async def _reviewed_today(db, user_id: int, since) -> bool:
    """Nothing to remind about if the student has already sat down today."""
    stmt = select(MistakeReview.id).where(
        MistakeReview.user_id == user_id,
        MistakeReview.last_reviewed_at >= since,
    )
    result = await db.execute(stmt)
    return result.first() is not None


async def _remind() -> int:
    now = utc_now()
    day_start = now - timedelta(hours=24)
    sent = 0

    async with CeleryAsyncSessionLocal() as db:
        repo = MistakeRepository(db)
        service = NotificationService(db)

        for user_id in await repo.users_with_due(now):
            if await _reviewed_today(db, user_id, day_start):
                continue
            if await _already_reminded_today(db, user_id, day_start):
                continue

            count = await repo.due_count(user_id, now)
            if count <= 0:
                continue

            await service.create_notification(
                NotificationCreateSchema(
                    recipient_id=user_id,
                    type=NotificationType.TEST_REMINDER,
                    action_type=NotificationActionType.OPEN_TEST,
                    title="Xatolar banki",
                    message=f"Bugun {count} ta savol takrorlashga tayyor.",
                    payload={"screen": "mistakes", "due": count},
                ),
                commit=False,
                # The student is not in the app at 08:00; the socket push would
                # go nowhere. The row itself is what they see on opening it.
                deliver=False,
            )
            sent += 1

        await db.commit()

    return sent


@celery_app.task(
    bind=True,
    name="quiz.remind_mistake_bank",
    queue="celery",
    max_retries=3,
    default_retry_delay=300,
)
def remind_mistake_bank(self) -> int:
    """Daily nudge for students with questions waiting in the bank."""
    try:
        return asyncio.run(_remind())
    except Exception as exc:
        logger.exception("Mistake bank reminder failed")
        raise self.retry(exc=exc)
