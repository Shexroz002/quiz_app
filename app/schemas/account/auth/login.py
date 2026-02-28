from typing import Annotated
from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.schemas.account.users import UserShortInfoSchema


class LoginSchema(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True
    )

    username: Annotated[
        str,
        Field(
            min_length=3,
            max_length=30,
            pattern="^[a-zA-Z0-9_]+$",
            description="Unique username, only letters, numbers, underscores"
        )
    ]
    password: Annotated[
        str,
        Field(
            min_length=6,
            description="Password must be at least 6 characters"
        )
    ]

    @field_validator("username", mode="before")
    @classmethod
    def _lower_username(cls, v: str) -> str:
        return v.lower()



class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class LoginResponse(TokenResponse):
    user: UserShortInfoSchema