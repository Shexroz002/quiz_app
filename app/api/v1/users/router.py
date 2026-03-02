from fastapi import APIRouter
from app.api.v1.users.endpoints import users_router
from app.api.v1.users.endpoints.contact import contact_router

user_router = APIRouter(prefix="", tags=["Users"])
user_router.include_router(users_router)
user_router.include_router(contact_router)
