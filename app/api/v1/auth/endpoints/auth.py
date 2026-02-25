from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.schemas.account.auth.register import RegisterSchema
from app.services.account.auth_service import AuthService, get_auth_service

login_router = APIRouter(prefix="/auth")


@login_router.post("/me/")
async def login(
        form_data: OAuth2PasswordRequestForm = Depends(),
        auth_service: AuthService = Depends(get_auth_service),
):
    return await auth_service.login(form_data.username, form_data.password)


@login_router.get("/me/")
async def me(current_user=Depends(get_current_user)):
    return current_user


@login_router.post("/register/", status_code=201)
async def register(
        user: RegisterSchema,
        auth_service: AuthService = Depends(get_auth_service),
):
    return await auth_service.register(user)
