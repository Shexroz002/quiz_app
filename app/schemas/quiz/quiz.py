import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.quiz.question import QuestionBase, QuestionListSchema


class QuizBase(BaseModel):
    id: int
    title: str


class QuizListSchema(QuizBase):
    created_at: datetime.datetime
    question_count: int = 0
    description: str | None = None
    subject: str | None = None
    is_new: bool = False


class QuizDetailSchema(QuizBase):
    description: str | None = None
    subject: str | None = None
    questions: list[QuestionListSchema] = []

    model_config = ConfigDict(from_attributes=True)


class QuizUpdateSchema(BaseModel):
    title: str


class TopicStatisticResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_name: str
    topic_name: str
    correct_answer: int
    wrong_answer: int
    total_answer: int
    percentage: float

class SubjectStatisticResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_name: str = Field(examples=["Matematika"])
    correct_answer: int = Field(examples=[12])
    wrong_answer: int = Field(examples=[8])
    total_answer: int = Field(examples=[20])
    percentage: float = Field(examples=[60.0])


class OverallStatisticCardsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_quiz_session: int = Field(examples=[156])
    correct_answer: int = Field(examples=[1248])
    average: Decimal = Field(examples=[Decimal("89.50")])