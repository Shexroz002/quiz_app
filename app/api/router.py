from fastapi import APIRouter

from app.api.v1.pdf_upload.pdf_parser import pdf_router
from app.api.v1.quiz.router import base_quiz_router
from app.api.v1.users.router import user_router
from app.api.v1.auth.router import auth_router

api_router = APIRouter()
api_router.include_router(user_router)
api_router.include_router(auth_router)
api_router.include_router(pdf_router)
api_router.include_router(base_quiz_router)
