from fastapi import APIRouter, Depends
from starlette import status

from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models.account.user import User
from app.schemas.account.users import ContactResponse
from app.services.account.contact_service import ContactService, get_contact_service

contact_router = APIRouter(prefix="/contact", tags=["Contact Management"])


@contact_router.get("/create/{friend_id}", status_code=status.HTTP_201_CREATED, response_model=ContactResponse)
async def create_contact(friend_id: int, contact_service: ContactService = Depends(get_contact_service),
                         current_user: User = Depends(get_current_user), ):
    return await contact_service.create_contact(friend_id, current_user.id)


@contact_router.get("/list/", response_model=list[ContactResponse])
async def contact_list(contact_service: ContactService = Depends(get_contact_service),
                       current_user: User = Depends(get_current_user)):
    return await contact_service.contact_list(current_user.id)
