from fastapi import APIRouter

from app.api.v1.subject.endpoint.subject import subject_router

base_subject_router = APIRouter(prefix="/subject", tags=["Subject"])

base_subject_router.include_router(subject_router)
