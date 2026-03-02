import datetime

from pydantic import BaseModel, ConfigDict
from app.schemas.quiz.question import QuestionBase, QuestionListSchema


class QuizBase(BaseModel):
    id: int
    title: str


class QuizListSchema(QuizBase):
    created_at: datetime.datetime
    question_count: int=0
    description: str | None = None
    subject: str | None = None
    is_new: bool = False


class QuizDetailSchema(QuizBase):
    description: str | None = None
    subject: str | None = None
    questions:list[QuestionListSchema] = []

    model_config = ConfigDict(from_attributes=True)

class QuizUpdateSchema(BaseModel):
    title: str
