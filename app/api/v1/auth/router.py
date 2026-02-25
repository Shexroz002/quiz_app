from fastapi import APIRouter

from app.api.v1.auth.endpoints import login_router

auth_router = APIRouter(prefix="", tags=["Auth"])

auth_router.include_router(login_router)
