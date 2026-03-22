import json
import redis
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from app.core.config import settings
from app.models.quiz.ai_quiz.pdf_to_quiz import PDFJobStatus, PDFJob

logger = logging.getLogger(__name__)



redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

def publish_job_event(job_id: str, payload: dict) -> None:
    try:
        redis_client.publish(f"pdf_job:{job_id}", json.dumps(payload))
    except Exception as e:
        logger.warning(f"Redis publish failed with {e}", exc_info=True)


async def update_job_status(
    db: AsyncSession,
    job_id: str,
    *,
    status: PDFJobStatus,
    progress: int,
    message: str | None = None,
    quiz_id: int | None = None,
    question_count: int | None = None,
    error: str | None = None,
):
    job = await db.get(PDFJob, job_id)
    if not job:
        return

    job.status = status
    job.progress = progress
    job.message = message
    job.quiz_id = quiz_id
    job.question_count = question_count
    job.error = error

    await db.commit()

    event_type = "progress"
    if status == PDFJobStatus.COMPLETED:
        event_type = "completed"
    elif status == PDFJobStatus.FAILED:
        event_type = "failed"

    publish_job_event(
        job_id,
        {
            "type": event_type,
            "job_id": str(job.id),
            "status": status.value,
            "progress": progress,
            "message": message,
            "quiz_id": quiz_id,
            "question_count": question_count,
            "error": error,
        },
    )