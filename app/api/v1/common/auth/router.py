from fastapi import APIRouter

from app.api.v1.common.auth.endpoints import login_router

auth_router = APIRouter(prefix="/auth", tags=["Auth"])

auth_router.include_router(login_router)
