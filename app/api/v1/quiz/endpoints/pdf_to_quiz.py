import uuid
import os
from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from app.services.pdf.tasks.quiz_tasks import process_pdf_task
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User

pdf_to_quiz_router = APIRouter(tags=["PDF to Quiz"])
UPLOAD_DIR= "media/quiz/file"

@pdf_to_quiz_router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...),current_user: User = Depends(get_current_user),):

    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Faqat PDF yuklash mumkin")

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    task = process_pdf_task.delay(file_path, current_user.id)

    return {
        "status": "queued",
        "task_id": task.id,
        "file_id": file_id,
    }
