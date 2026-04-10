from datetime import datetime

from pydantic import BaseModel, field_serializer

from app.schemas.quiz.question import BASE_URL


class TeacherAnalyticsCardItem(BaseModel):
    value: int | float
    change_percent: int
    trend: str
    label: str
    sub_label: str | None = None

    @field_serializer("value")
    def serialize_value(self, value):
        if isinstance(value, float):
            return round(value, 2)
        return value


class TeacherAnalyticsOverviewResponse(BaseModel):
    average_score: TeacherAnalyticsCardItem
    completed_tests: TeacherAnalyticsCardItem
    active_students: TeacherAnalyticsCardItem
    weak_topics: TeacherAnalyticsCardItem

from pydantic import BaseModel, field_serializer


class TeacherGroupResultsResponse(BaseModel):
    rank: int
    group_id: int
    group_name: str
    student_count: int
    tests_count: int
    average_score: float
    progress_percent: float
    performance_level: str
    performance_color: str

    @field_serializer("average_score", "progress_percent")
    def serialize_float_fields(self, value: float) -> float:
        return round(value, 2)

class TeacherWeakTopicsResponse(BaseModel):
    rank: int
    topic_name: str
    subject_name: str | None = None
    wrong_count: int
    average_percent: float
    progress_percent: float
    severity: str
    color: str

    @field_serializer("average_percent", "progress_percent")
    def serialize_float_fields(self, value: float) -> float:
        return round(value, 2)


class WeakStudentsResponse(BaseModel):
    student_id: int
    full_name: str
    username: str | None = None
    group_names: list[str]
    profile_image: str | None
    average_score: float
    tests_count: int
    last_activity: datetime | None = None
    performance_color: str

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

class WeakStudentsFilterParams(BaseModel):
    search: str | None = None
    group_id: int | None = None
    min_score: float | None = None
    max_score: float | None = 75