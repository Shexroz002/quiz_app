from pydantic import BaseModel, ConfigDict
from app.schemas.quiz.question import QuestionBase


class QuizBase(BaseModel):
    id: int
    title: str


class QuizListSchema(QuizBase):
    pass

class QuizDetailSchema(QuizBase):
    questions: list[QuestionBase]

    model_config = ConfigDict(from_attributes=True)

class QuizUpdateSchema(BaseModel):
    title: str
