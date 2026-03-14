from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.schemas.account.auth.login import LoginResponse, RefreshRequest, TokenResponse
from app.schemas.account.auth.register import RegisterSchema
from app.schemas.account.users import UserShortInfoSchema, UserDetailInfoSchema
from app.services.account.auth_service import AuthService, get_auth_service

login_router = APIRouter(prefix="/auth")


@login_router.post("/me/",status_code=200,response_model=LoginResponse)
async def login(
        form_data: OAuth2PasswordRequestForm = Depends(),
        auth_service: AuthService = Depends(get_auth_service),
):
    return await auth_service.login(form_data.username, form_data.password)

@login_router.post("/refresh/", response_model=TokenResponse)
async def refresh_token(
        refresh_request: RefreshRequest,
        auth_service: AuthService = Depends(get_auth_service),
):
    return await auth_service.refresh(refresh_request.refresh_token)

@login_router.get("/me/",response_model=UserDetailInfoSchema)
async def me(current_user=Depends(get_current_user), auth_service: AuthService = Depends(get_auth_service)):
    return await auth_service.user_full_information(current_user.id)


@login_router.post("/register/", status_code=201, response_model=UserShortInfoSchema)
async def register(
        user: RegisterSchema,
        auth_service: AuthService = Depends(get_auth_service),
):
    return await auth_service.register(user)
