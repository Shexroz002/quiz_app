from fastapi import APIRouter
from app.api.v1.common.users.endpoints import users_router
from app.api.v1.common.users.endpoints.contact import contact_router

user_router = APIRouter(prefix="/users", tags=["Users"])
user_router.include_router(users_router)
user_router.include_router(contact_router)
