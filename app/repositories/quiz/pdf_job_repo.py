from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz.ai_quiz.pdf_to_quiz import PDFJob, PDFJobStatus


class PDFJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, job: PDFJob) -> PDFJob:
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_by_id(self, job_id: str) -> PDFJob | None:
        return await self.db.get(PDFJob, job_id)

    async def set_task_id(self, job: PDFJob, task_id: str) -> PDFJob:
        job.celery_task_id = task_id
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def update_status(
        self,
        job: PDFJob,
        status: PDFJobStatus,
        progress: int,
        message: str | None = None,
        quiz_id: int | None = None,
        question_count: int | None = None,
        error: str | None = None,
    ) -> PDFJob:
        job.status = status
        job.progress = progress
        job.message = message
        job.quiz_id = quiz_id
        job.question_count = question_count
        job.error = error

        await self.db.commit()
        await self.db.refresh(job)
        return job