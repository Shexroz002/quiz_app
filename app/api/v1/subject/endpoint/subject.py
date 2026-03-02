from typing import List
from fastapi import APIRouter, Depends
from app.schemas.subject.subject import SubjectIdListSchema

from app.services.subject.subject_service import get_subject_service

subject_router = APIRouter(prefix="", tags=["Quiz Management"])


@subject_router.get("/list/", response_model=List[SubjectIdListSchema])
async def list_quizzes(subject_service=Depends(get_subject_service)):
    return await subject_service.list()
