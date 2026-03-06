from pydantic import BaseModel

from app.schemas.account.users import UserShortInfoSchema


class Contact(BaseModel):
    id: int
    name: str


class ContactRequest(BaseModel):
    friend_id: int

class ContactResponse(BaseModel):
    id: int
    # name: str
    friend:UserShortInfoSchema