from typing import Annotated

from pydantic import BaseModel, Field, EmailStr


class UserListSchema(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str


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
    profile_image: str | None = None

    class Config:
        orm_mode = True
