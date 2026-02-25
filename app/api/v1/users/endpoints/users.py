from fastapi import APIRouter, Depends, UploadFile, File
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models.account.user import User
from app.schemas.account.users import UserListSchema, UpdateUserSchema
from app.services.account.users import UserService, get_user_service

users_router = APIRouter(prefix="/users")


@users_router.get("/", response_model=list[UserListSchema])
async def list_users(user_service: UserService = Depends(get_user_service)):
    return await user_service.list()


@users_router.get("/{user_id}/", response_model=UserListSchema)
async def get_user(user_id: int, user_service: UserService = Depends(get_user_service)):
    return await user_service.get(user_id)


@users_router.put("/{user_id}/avatar/")
async def upload_avatar(
        user_id: int,
        avatar: UploadFile = File(...),
        user_service: UserService = Depends(get_user_service)
):
    return await user_service.upload_avatar(user_id, avatar)


@users_router.put("/{user_id}/", response_model=UpdateUserSchema)
async def update_user(
        user_id: int,
        user_update: UpdateUserSchema,
        user_service: UserService = Depends(get_user_service),
        current_user: User = Depends(get_current_user),
):
    return await user_service.update_user(user_id, current_user, user_update)
