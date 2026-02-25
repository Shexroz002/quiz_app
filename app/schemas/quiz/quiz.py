from pydantic import BaseModel
from app.schemas.quiz.question import QuestionBase


class QuizBase(BaseModel):
    id: int
    title: str


class QuizListSchema(QuizBase):
    pass

class QuizDetailSchema(QuizBase):
    questions: list[QuestionBase]

    class Config:
        orm_mode = True

class QuizUpdateSchema(BaseModel):
    title: str