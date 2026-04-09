from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_serializer

from app.models.account.user import EducationLevel
from app.schemas.quiz.question import BASE_URL
from app.schemas.subject.subject import SubjectBase, SubjectIdListSchema


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
    first_name: str | None = Field(
        ...,
        min_length=2,
        max_length=50,
        description="First name should be between 2 and 50 characters"
    )
    last_name: str | None = Field(
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
    role: str | None = None
    profile_image: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"


class UserSubjectSchema(BaseModel):
    id: int
    subject: SubjectIdListSchema

    model_config = ConfigDict(from_attributes=True)


class UserDetailInfoSchema(UserShortInfoSchema):
    email: EmailStr | None
    phone_number: str | None
    school_name: str | None
    education_level: str | None
    subjects: list[UserSubjectSchema] = []

    model_config = ConfigDict(from_attributes=True)


class UserDetailPatchSchema(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone_number: str | None = None
    school_name: str | None = None
    education_level: EducationLevel | None = None
    subject_ids: list[int] | None = None


class StudentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


from datetime import datetime
from pydantic import BaseModel, Field


class StudentTableItemSchema(BaseModel):
    student_id: int
    username: str
    profile_image: str | None = None
    full_name: str = Field(
        default="Toshmatov Diyorbek",
        description="O'quvchi F.I.Sh"
    )

    group_names: list = Field(
        default=["1A maxsus",],
        description="Sinf nomi"
    )

    average_score: float = Field(
        default=67,
        ge=0,
        le=100,
        description="O'rtacha ball"
    )

    tests_count: int = Field(
        default=12,
        ge=0,
        description="Ishlagan testlar soni"
    )

    last_activity: datetime | None = Field(
        default_factory=datetime.now,
        description="So'nggi faoliyat vaqti"
    )

    status: StudentStatus = Field(
        default=StudentStatus.ACTIVE,
        description="O'quvchi holati"
    )

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"
