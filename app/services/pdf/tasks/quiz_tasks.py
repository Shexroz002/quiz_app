import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.database.base import CeleryAsyncSessionLocal
from app.core.database.session import AsyncSessionLocal
from app.models.quiz.ai_quiz.pdf_to_quiz import PDFJob, PDFJobStatus
from app.services.ai.promt import QUIZ_SCHEMA, QUIZ_PROMPT
from app.services.pdf.redis_pubsub_service import update_job_status
from app.services.quiz.quiz_service import save_quiz_from_json
import os

logger = logging.getLogger(__name__)

from app.services.ai.providers.provider_factory import get_provider
from app.services.ai.ai_service import AIQuizParser as UniversalAIQuizParser
from app.core.config import settings


@celery_app.task(bind=True, queue="pdf_ai_queue", max_retries=3, default_retry_delay=10)
def process_pdf_task(self, job_id: str):
    async def runner():
        async with CeleryAsyncSessionLocal() as db:
            job = await db.get(PDFJob, job_id)
            if not job:
                raise ValueError(f"Job topilmadi: {job_id}")

            # ✅ progress service (sizda update_job_status bor)
            await update_job_status(
                db=db,
                job_id=job_id,
                status=PDFJobStatus.PROCESSING,
                progress=10,
                message="Fayl tahlilga tayyorlanmoqda",
            )

            async def parser_progress(progress: int, message: str):
                await update_job_status(
                    db=db,
                    job_id=job_id,
                    status=PDFJobStatus.PROCESSING,
                    progress=progress,
                    message=message,
                )

            # ✅ 1) Provider tanlash (default gemini yoki DB'dan)
            provider_name = getattr(job, "ai_provider", None) or "gemini"
            provider = get_provider(provider_name, logger=logger)

            # ✅ 2) Universal parser yaratish (prompt + schema)
            parser = UniversalAIQuizParser(
                provider=provider,
                prompt=QUIZ_PROMPT,  # yoki sizdagi prompt variable
                schema=QUIZ_SCHEMA,  # sizning schema
            )

            # ✅ 3) parse (progress callback bilan)
            result = await parser.parse_pdf(
                pdf_path=job.file_path,
                progress=parser_progress,  # universal parser "progress" deb oladi
                timeout_sec=120,
            )

            await update_job_status(
                db=db,
                job_id=job_id,
                status=PDFJobStatus.PROCESSING,
                progress=85,
                message="Savollar bazaga saqlanmoqda",
            )

            quiz_id, question_count = await save_quiz_from_json(
                db=db,
                data=result,
                pdf_path=job.file_path,
                user_id=job.user_id,
            )

            await update_job_status(
                db=db,
                job_id=job_id,
                status=PDFJobStatus.COMPLETED,
                progress=100,
                message="Test tayyor bo‘ldi",
                quiz_id=quiz_id,
                question_count=question_count,
            )

            # cleanup
            if os.path.exists(job.file_path):
                os.remove(job.file_path)


    try:
        asyncio.run(runner())
    except Exception as e:
        logger.exception("PDF processing taskda xatolik yuz berdi: %s", str(e))
