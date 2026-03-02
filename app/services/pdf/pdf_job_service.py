import os
import uuid
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz.ai_quiz.pdf_to_quiz import PDFJob, PDFJobStatus
from app.repositories.quiz.pdf_job_repo import PDFJobRepository
from app.services.pdf.storage_service import StorageService
from app.services.pdf.tasks import process_pdf_task


class PDFJobService:
    def __init__(self, db: AsyncSession, storage: StorageService):
        self.db = db
        self.repo = PDFJobRepository(db)
        self.storage = storage

    async def create_job_and_queue(self, *, file: UploadFile, user_id: int) -> PDFJob:

        if not file.filename:
            raise HTTPException(400, "Fayl nomi topilmadi")

        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Faqat PDF yuklash mumkin")

        if file.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(400, "Noto‘g‘ri fayl turi, faqat PDF qabul qilinadi")


        job_id = uuid.uuid4()
        file_path = os.path.join(self.storage.upload_dir, f"{job_id}.pdf")

        await self.storage.save_pdf(file, file_path)

        job = PDFJob(
            id=job_id,
            user_id=user_id,
            file_name=file.filename,
            file_path=file_path,
            status=PDFJobStatus.QUEUED,
            progress=0,
            message="Fayl qabul qilindi",
        )
        job_new = await self.repo.create(job)

        task = process_pdf_task.delay(str(job.id))
        await self.repo.set_task_id(job, task.id)

        return job_new