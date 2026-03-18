import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.celery_app import celery_app
from app.core.database.base import CeleryAsyncSessionLocal
from app.models.quiz.ai_quiz.pdf_to_quiz import PDFJob, PDFJobStatus
from app.services.ai.ai_service import AIQuizParser as UniversalAIQuizParser
from app.services.ai.promt import QUIZ_PROMPT, QUIZ_SCHEMA, ai_generator_by_description
from app.services.ai.providers.provider_factory import get_provider
from app.services.pdf.redis_pubsub_service import update_job_status
from app.services.quiz.quiz_service import save_quiz_from_json

logger = logging.getLogger(__name__)

ProgressCb = Callable[[int, str, str | None], Awaitable[None]]


class AIQuizTaskService:
    """
    Celery tasklar uchun umumiy servis.
    Mas'uliyatlari:
    - job olish
    - progress update qilish
    - provider/parser yaratish
    - AI result olish
    - resultni bazaga saqlash
    - job statusni yakunlash
    """

    def __init__(self, db, logger_: logging.Logger):
        self.db = db
        self.logger = logger_

    async def _get_job_or_raise(self, job_id: str) -> PDFJob:
        job = await self.db.get(PDFJob, job_id)
        if not job:
            raise ValueError(f"Job topilmadi: {job_id}")
        return job

    async def _update_status(
            self,
            *,
            job_id: str,
            status: PDFJobStatus,
            progress: int,
            message: str,
            error: str | None = None,
            quiz_id: int | None = None,
            question_count: int | None = None,
    ) -> None:
        await update_job_status(
            db=self.db,
            job_id=job_id,
            status=status,
            progress=progress,
            message=message,
            error=error,
            quiz_id=quiz_id,
            question_count=question_count,
        )

    def _build_progress_callback(self, job_id: str) -> ProgressCb:
        async def parser_progress(
                progress: int,
                message: str,
                error: str | None = None,
        ) -> None:
            if error:
                await self._update_status(
                    job_id=job_id,
                    status=PDFJobStatus.FAILED,
                    progress=progress,
                    message=message,
                    error=error,
                )
                return

            await self._update_status(
                job_id=job_id,
                status=PDFJobStatus.PROCESSING,
                progress=progress,
                message=message,
            )

        return parser_progress

    def _build_parser(self, provider_name: str | None) -> UniversalAIQuizParser:
        provider = get_provider(provider_name or "gemini", logger=self.logger)
        return UniversalAIQuizParser(
            provider=provider,
            prompt=QUIZ_PROMPT,
            schema=QUIZ_SCHEMA,
        )

    async def _save_result(
            self,
            *,
            job: PDFJob,
            data: dict[str, Any],
            progress: ProgressCb,
    ) -> tuple[int, int]:
        await self._update_status(
            job_id=str(job.id),
            status=PDFJobStatus.PROCESSING,
            progress=85,
            message="Savollar bazaga saqlanmoqda",
        )

        quiz_id, question_count = await save_quiz_from_json(
            db=self.db,
            data=data,
            pdf_path=job.file_path,
            user_id=job.user_id,
            progress=progress,
        )
        return quiz_id, question_count

    async def _complete_job(
            self,
            *,
            job_id: str,
            quiz_id: int,
            question_count: int,
    ) -> None:
        await self._update_status(
            job_id=job_id,
            status=PDFJobStatus.COMPLETED,
            progress=100,
            message="Test tayyor bo‘ldi",
            quiz_id=quiz_id,
            question_count=question_count,
        )

    @staticmethod
    async def _cleanup_file(file_path: str | None) -> None:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

    async def process_pdf(self, job_id: str) -> None:
        job = await self._get_job_or_raise(job_id)

        await self._update_status(
            job_id=job_id,
            status=PDFJobStatus.PROCESSING,
            progress=10,
            message="Fayl tahlilga tayyorlanmoqda",
        )

        progress_cb = self._build_progress_callback(job_id)
        parser = self._build_parser(getattr(job, "ai_provider", None))

        result = await parser.parse_pdf(
            pdf_path=job.file_path,
            progress=progress_cb,
            timeout_sec=120,
        )

        quiz_id, question_count = await self._save_result(
            job=job,
            data=result,
            progress=progress_cb,
        )

        await self._complete_job(
            job_id=job_id,
            quiz_id=quiz_id,
            question_count=question_count,
        )

        await self._cleanup_file(job.file_path)

    async def generate_from_description(self, job_id) -> None:
        result = await self.db.execute(
            select(PDFJob)
            .options(joinedload(PDFJob.subject_rel))
            .where(PDFJob.id == job_id)
        )

        job = result.scalar_one_or_none()

        if job and job.subject_rel:
            subject_name = job.subject_rel.name
        else:
            subject_name = None

        await self._update_status(
            job_id=job_id,
            status=PDFJobStatus.PROCESSING,
            progress=10,
            message="Test generatori tayyorlanmoqda...",
        )

        progress_cb = self._build_progress_callback(job_id)
        provider = get_provider("gemini", logger=self.logger)
        prompt = ai_generator_by_description(subject_name, job.description, job.number_questions)
        parser = UniversalAIQuizParser(
            provider=provider,
            prompt=prompt,
            schema=QUIZ_SCHEMA,
        )

        result = await parser.quiz_generate_by_description(
            progress=progress_cb,
            timeout_sec=120,
        )
        logger.info("AI javobi: %s", result)
        quiz_id, question_count = await self._save_result(
            job=job,
            data=result,
            progress=progress_cb,
        )

        await self._complete_job(
            job_id=job_id,
            quiz_id=quiz_id,
            question_count=question_count,
        )


def _run_async_task(coro) -> None:
    try:
        asyncio.run(coro)
    except Exception as exc:
        logger.exception("AI taskda xatolik yuz berdi: %s", str(exc))
        raise exc


@celery_app.task(
    bind=True,
    name="process_pdf_task",
    queue="pdf_ai_queue",
    max_retries=3,
    default_retry_delay=10,
)
def process_pdf_task(self, job_id: str) -> None:
    async def runner():
        async with CeleryAsyncSessionLocal() as db:
            service = AIQuizTaskService(db=db, logger_=logger)
            await service.process_pdf(job_id)

    _run_async_task(runner())


@celery_app.task(
    bind=True,
    name="generate_quiz_from_description_task",
    queue="ai_test_generator",
    max_retries=3,
    default_retry_delay=10,
)
def generate_quiz_from_description_task(self, job_id) -> None:
    async def runner():
        async with CeleryAsyncSessionLocal() as db:
            service = AIQuizTaskService(db=db, logger_=logger)
            await service.generate_from_description(job_id)

    _run_async_task(runner())
