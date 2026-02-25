from typing import Annotated
from pydantic import Field,model_serializer, field_validator

from app.core.security.password_hash import hash_password
from app.schemas.account.auth.login import LoginSchema


class RegisterSchema(LoginSchema):
    first_name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=50,
            description="First name should be between 2 and 50 characters"
        )
    ]
    last_name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=50,
            description="Last name should be between 2 and 50 characters"
        )
    ]

    @field_validator("username", mode="before")
    @classmethod
    def _lower_username(cls, v: str) -> str:
        return v.lower()

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _capitalize_names(cls, v: str) -> str:
        return v.capitalize() if isinstance(v, str) else v

    @model_serializer
    def serialize(self):
        return {
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "password_hash": hash_password(self.password)

        }


