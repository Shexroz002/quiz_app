from datetime import date
from pydantic import BaseModel, field_serializer


class TeacherActivityChartItem(BaseModel):
    day_key: str
    date: date
    submitted_tests: int
    average_score: float
    participated_students: int

    @field_serializer("average_score")
    def serialize_average_score(self, value: float) -> float:
        return round(value, 2)


class TeacherActivityChartResponse(BaseModel):
    trend_percent: int
    trend_label: str
    items: list[TeacherActivityChartItem]