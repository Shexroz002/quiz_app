from typing import Annotated

from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_serializer

from app.schemas.quiz.question import BASE_URL


class UserListSchema(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    profile_image: str | None = None

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"

class UserContactListSchema(UserListSchema):
    contact_available: bool

class UpdateUserSchema(BaseModel):
    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=30,
        pattern=r"^[a-zA-Z0-9_]+$",
        description="Unique username, only letters, numbers, underscores",
    )
    first_name: str| None = Field(
        ...,
        min_length=2,
        max_length=50,
        description="First name should be between 2 and 50 characters"
    )
    last_name: str| None = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Last name should be between 2 and 50 characters"
    )


class UserShortInfoSchema(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    role: str|None=None
    profile_image: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"
