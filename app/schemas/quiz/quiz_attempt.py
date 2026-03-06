from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field, ConfigDict


class SubmitAnswerRequest(BaseModel):
    question_id: int
    selected_option: str

class AnswerItem(BaseModel):
    question_id: int
    selected_option: str = Field(..., pattern="^[ABCD]$")

class SubmitAnswerResponse(BaseModel):
    question_id: int
    selected_option: str



class TopicStatisticSchema(BaseModel):
    topic_name:str
    total_questions: int
    correct_answers: int

class FinishQuizResponse(BaseModel):
    session_id: int
    attempt_id: int
    total_questions: int
    answered_questions: int
    correct_answers: int
    wrong_answers: int
    spend_time: int
    score: int
    finished: bool
    topic_statistic:List[TopicStatisticSchema]


class ParticipantAttemptRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int

    first_name: str | None = None
    last_name: str | None = None
    profile_image: str | None = None

    score: int | None = None
    wrong_answers: int | None = None
    total_questions: int | None = None

    finished: bool | None = None

    spend_time_seconds: Decimal | float | None = None
    finished_at: datetime | None = None