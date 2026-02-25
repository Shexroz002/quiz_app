import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.database.session import AsyncSessionLocal
from app.services.ai.ai_service import AIQuizParser
from app.services.quiz.quiz_service import save_quiz_from_json

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, queue="pdf_ai_queue")
def process_pdf_task(self, pdf_path: str, user_id: int):
    async def runner():
        parser = AIQuizParser()
        async with AsyncSessionLocal() as db:
            result = parser.parse_pdf(pdf_path)

            if isinstance(result, dict) and result.get("error"):
                raise Exception(result["error"])
            print("Saved")
            await save_quiz_from_json(db, result, pdf_path, user_id)

    try:
        asyncio.run(runner())
    except Exception as e:
        logger.exception("Celery task failed")
        raise self.retry(exc=e, countdown=10)
