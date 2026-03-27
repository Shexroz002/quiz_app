from pydantic import BaseModel, Field
from typing import Optional

from app.models.quiz.quiz import QuizGenerateType


class TeacherQuizListFilterSchema(BaseModel):
    search: Optional[str] = Field(None, description="Quiz title bo'yicha qidiruv")
    quiz_generate_type: Optional[QuizGenerateType] = Field(
        None,
        description="Quiz generate type filter"
    )
    page: int = Field(1, ge=1)
    size: int = Field(10, ge=1, le=100)