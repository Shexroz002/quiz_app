from fastapi import APIRouter, Depends
from starlette import status
from fastapi.responses import JSONResponse
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models.account.user import User
from app.schemas.account.users import ContactResponse, UserShortInfoSchema
from app.services.account.contact_service import ContactService, get_contact_service

contact_router = APIRouter(prefix="/contact", tags=["Contact Management"])


@contact_router.get("/create/{friend_id}", status_code=status.HTTP_201_CREATED)
async def create_contact(friend_id: int, contact_service: ContactService = Depends(get_contact_service),
                         current_user: User = Depends(get_current_user), ):
    await contact_service.create_contact(current_user.id, friend_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"message": "Contact created successfully."})


@contact_router.get("/list/", response_model=list[ContactResponse])
async def contact_list(contact_service: ContactService = Depends(get_contact_service),
                       current_user: User = Depends(get_current_user)):
    return await contact_service.contact_list(current_user.id)

@contact_router.get("/suggestions/", response_model=list[UserShortInfoSchema])
async def contact_suggestions(contact_service: ContactService = Depends(get_contact_service),
                       current_user: User = Depends(get_current_user)):
    return await contact_service.contact_suggestions(current_user.id)