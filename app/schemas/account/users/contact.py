from datetime import datetime

from pydantic import BaseModel, computed_field, field_serializer, ConfigDict

from app.schemas.account.users import UserShortInfoSchema
from app.schemas.quiz.question import BASE_URL


class Contact(BaseModel):
    id: int
    name: str


class ContactRequest(BaseModel):
    friend_id: int


class ContactResponse(BaseModel):
    id: int
    # name: str
    friend: UserShortInfoSchema


class StudentCardResponse(BaseModel):
    student_id: int
    full_name: str
    username: str
    group_names: list[str] | None = []

    average_score: float | None = None
    total_tests: int | None = 0
    last_activity: datetime | None = None
    profile_image: str | None = None

    @field_serializer("average_score")
    def serialize_avg(self, value):
        if value is None:
            return 0
        return round(value, 2)

    @computed_field
    @property
    def last_activity_label(self) -> str | None:
        if not self.last_activity:
            return None
        return self.last_activity.isoformat()

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"


class WeakTopicItemResponse(BaseModel):
    subject_name: str | None
    topic_name: str
    average_percent: float
    level: str

    @field_serializer("average_percent")
    def serialize_average_percent(self, value: float) -> float:
        return round(value, 2)


class SubjectStatItem(BaseModel):
    subject_name: str
    average_percent: float

    @field_serializer("average_percent")
    def serialize_percent(self, value):
        return round(value, 0)  # UI dagi kabi butun son


class SubjectStatsResponse(BaseModel):
    overall_percent: float
    items: list[SubjectStatItem]

    @field_serializer("overall_percent")
    def serialize_overall(self, value):
        return round(value, 0)


class TeacherStudentLeaderboardItem(BaseModel):
    student_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str
    profile_image: str | None = None

    group_names: list[str]

    average_score: float
    tests_count: int
    streak_days: int
    last_activity: datetime | None
    status: str

    @field_serializer("average_score")
    def serialize_average_score(self, value: float) -> float:
        return round(value, 2)

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"


class TeacherStudentListParams(BaseModel):
    search: str | None = None
    min_score: float | None = None
    max_score: float | None = None
    status: str | None = None
    ordering: str | None = None
