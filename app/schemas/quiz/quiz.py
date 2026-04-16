import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.quiz.quiz import QuizGenerateType
from app.schemas.quiz.question import QuestionListSchema


class TeacherQuizListItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str = Field(..., description="Test nomi")
    subject: Optional[str] = Field(None, description="Fan nomi")
    quiz_generate_type: QuizGenerateType = Field(..., description="Test turi")

    question_count: int = Field(0, description="Savollar soni")
    attempts: int = Field(0, description="Urinishlar soni")
    average_score: Decimal = Field(0, description="O'rtacha ball")
    created_at: datetime.datetime = Field(..., description="Yaratilgan sana")

class QuizBase(BaseModel):
    id: int
    title: str


class QuizListSchema(BaseModel):
    created_at: datetime.datetime
    question_count: int = 0
    description: str | None = None
    subject: str | None = None
    is_new: bool = False
    quiz_id:int
    title: str
    quiz_generate_type: QuizGenerateType = Field(..., description="Test turi")


class QuizDetailSchema(QuizBase):
    description: str | None = None
    subject: str | None = None
    quiz_generate_type: QuizGenerateType = Field(..., description="Test turi")
    questions: list[QuestionListSchema] = []

    model_config = ConfigDict(from_attributes=True)


class QuizUpdateSchema(BaseModel):
    title: str
    quiz_generate_type: QuizGenerateType = Field(..., description="Test turi")
    subject: Optional[str] = Field(None, description="Fan nomi")
    description: Optional[str] = Field(None, description="Test tavsifi")
class QuizStatisticsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_attempts: int = Field(
        default=0,
        ge=0,
        description="Jami urinishlar soni",
        examples=[48],
    )
    average_score: float = Field(
        default=0,
        ge=0,
        le=100,
        description="O'rtacha ball foizda",
        examples=[69.0],
    )
    completion_rate: float = Field(
        default=0,
        ge=0,
        le=100,
        description="Bajarilish darajasi foizda",
        examples=[69.0],
    )
    success_rate: float = Field(
        default=0,
        ge=0,
        le=100,
        description="Muvaffaqiyat foizda",
        examples=[55.0],
    )
    highest_score: float = Field(
        default=0,
        ge=0,
        le=100,
        description="Eng yuqori ball foizda",
        examples=[91.0],
    )
    champions_count: int = Field(
        default=0,
        ge=0,
        description="A'lochilar soni",
        examples=[7],
    )

class TopicStatisticResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_name: str
    topic_name: str
    correct_answer: int
    wrong_answer: int
    total_answer: int
    percentage: float
    first_test_date: datetime.date | None = Field(examples=[datetime.date(2021, 1, 1)])
    last_test_date: datetime.date | None = Field(examples=[datetime.date(2021, 12, 31)])

class SubjectStatisticResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_name: str = Field(examples=["Matematika"])
    correct_answer: int = Field(examples=[12])
    wrong_answer: int = Field(examples=[8])
    total_answer: int = Field(examples=[20])
    percentage: float = Field(examples=[60.0])
    first_attempt_date: datetime.date | None = Field(examples=[datetime.date(2021, 1, 1)])
    last_attempt_date: datetime.date | None = Field(examples=[datetime.date(2021, 12, 31)])


class OverallStatisticCardsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_quiz_session: int|None = Field(examples=[156])
    correct_answer: int|None = Field(examples=[1248])
    average: Decimal|None = Field(examples=[Decimal("89.50")])