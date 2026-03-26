from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from typing import List

from app.models.group.student_group import GroupColor, GroupStatus
from app.schemas.quiz.question import BASE_URL


class StudentGroupCreateSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    subject_id: int | None = None
    color: GroupColor = GroupColor.TEAL
    description: str | None = Field(default=None, max_length=1000)
    student_ids: List[int] = Field(default_factory=list)
    cover_image: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid")


class StudentGroupUpdateSchema(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    subject_id: int | None = None
    color: GroupColor | None = None
    description: str | None = Field(default=None, max_length=1000)
    status: GroupStatus | None = None

    model_config = ConfigDict(extra="forbid")


class StudentGroupMemberShortSchema(BaseModel):
    student_id: int
    full_name: str
    username: str
    profile_image: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StudentGroupResponseSchema(BaseModel):
    id: int
    name: str
    subject_id: int | None = None
    color: GroupColor
    cover_image: str | None = None
    description: str | None = None
    status: GroupStatus
    teacher_id: int
    members_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class StudentGroupCardSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    subject_name: str | None = None
    description: str | None = None
    students_count: int = 0
    tests_count: int = 0
    average_score: float = 0
    status: str
    last_activity: datetime | None = None
    color: str | None = None
    cover_image: str | None = None

    @field_serializer("cover_image")
    def add_base_url(self, value: str):
        if value is None or value == "":
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"


class StudentGroupDetailSchema(StudentGroupResponseSchema):
    members: list[StudentGroupMemberShortSchema] = []


class GroupCoverImageResponseSchema(BaseModel):
    cover_image: str | None = Field(default=None, max_length=255)

    @field_serializer("cover_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"


from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_serializer


class GroupMemberTableItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: int
    full_name: str = Field(..., description="O'quvchi F.I.Sh")
    profile_image: str | None = Field(default=None, description="Profil rasmi")
    gender: str | None = Field(default=None, description="Jinsi")
    phone_number: str | None = Field(default=None, description="Telefon raqami")
    birth_date: date | None = Field(default=None, description="Tug'ilgan sana")

    @field_serializer("profile_image")
    def add_base_url(self, value: str | None):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"