from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database.base import get_db
from app.models.quiz import PDFJob
from app.services.pdf.pdf_job_service import PDFJobService
from app.services.pdf.storage_service import StorageService
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User

pdf_to_quiz_router = APIRouter(prefix="/jop", tags=["PDF Jobs"])


@pdf_to_quiz_router.post("/pdf-jobs")
async def create_pdf_job(
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    storage = StorageService(
        upload_dir=settings.UPLOAD_DIR,
        max_size_bytes=settings.MAX_PDF_SIZE,
    )
    service = PDFJobService(db=db, storage=storage)

    job = await service.create_job_and_queue(file=file, user_id=current_user.id)

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "progress": job.progress,
        "message": job.message,
        "task_id": job.celery_task_id
    }


@pdf_to_quiz_router.get("/jobs/{job_id}")
async def get_pdf_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(PDFJob, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job topilmadi")

    return {
        "job_id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "quiz_id": job.quiz_id,
        "question_count": job.question_count,
        "error": job.error,
    }