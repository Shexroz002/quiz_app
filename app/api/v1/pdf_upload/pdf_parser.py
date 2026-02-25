import json
import os
import uuid
import re

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User
from app.models.quiz import Quiz, Question, Option, QuestionImage
from app.schemas.quiz.quiz import  QuizBase
from app.core.database.base import get_db
from app.services.pdf.pdf_service import PDFService
from app.services.pdf.tasks.quiz_tasks import process_pdf_task
from app.services.quiz.quiz_service import save_quiz_from_json
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
pdf_router = APIRouter()

UPLOAD_DIR = "media/quiz/file"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@pdf_router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...),current_user: User = Depends(get_current_user),):

    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Faqat PDF yuklash mumkin")

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")

    # save file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    print("File saved to:", file_path)
    task = process_pdf_task.delay(file_path, current_user.id)

    return {
        "status": "queued",
        "task_id": task.id,
        "file_id": file_id,
    }


@pdf_router.get("/task-status/{task_id}")
def get_task_status(task_id: str):
    from celery.result import AsyncResult

    task_result = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None,
    }
from pathlib import Path
TXT_DIR = Path("media/quiz/txt")


# ---------------------------
# JSON CLEANERS
# ---------------------------

INVALID_BACKSLASH_RE = re.compile(r'\\(?!["\\/bfnrtu])')
CODE_BLOCK_RE = re.compile(r"```(?:json)?|```", re.IGNORECASE)


def fix_invalid_backslashes(text: str) -> str:
    """Invalid JSON backslashlarni fix qiladi."""
    return INVALID_BACKSLASH_RE.sub(r"\\\\", text)


def extract_json_block(text: str) -> str:
    """
    AI yoki TXT ichidan JSON qismini ajratib oladi.
    """
    text = CODE_BLOCK_RE.sub("", text).strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("JSON object not found inside TXT")

    return text[start:end + 1]


def parse_dirty_json(text: str) -> dict:
    """
    Dirty JSON → valid Python dict
    """
    try:
        json_data = json.loads(text)
        print("JSON to'g'ri formatda:", json_data)
    except json.JSONDecodeError as e:
        pass
    text = extract_json_block(text)
    text = fix_invalid_backslashes(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # debugging uchun kichik snippet qaytaramiz
        error_context = text[max(0, e.pos - 80): e.pos + 80]
        raise ValueError(f"{e.msg} near:\n{error_context}") from e


# ---------------------------
# API ENDPOINT
# ---------------------------

@pdf_router.get("/txt-to-json/{file_id}")
async def txt_to_json(file_id: str,db=Depends(get_db)):
    txt_path = TXT_DIR / f"{file_id}.txt"
    if not txt_path.exists():
        raise HTTPException(404, "TXT file not found")

    with open(txt_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            data = parse_dirty_json(raw_text)
        except ValueError as e:
            raise HTTPException(400, f"JSON parsing error: {e}")
    await save_quiz_from_json(db, data, f"media/quiz/file/{file_id}.pdf", 5)

    return {
        "status": "success",
    }

#get quiz by quiz_id
@pdf_router.get("/quiz/{quiz_id}", response_model=QuizBase)
async def get_quiz(
    quiz_id: int,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Quiz)
        .where(Quiz.id == quiz_id)
        .options(
            selectinload(Quiz.questions)
            .selectinload(Question.options),
            selectinload(Quiz.questions)
            .selectinload(Question.images),
        )
    )

    result = await db.execute(stmt)
    quiz = result.scalar_one_or_none()

    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")

    return quiz


