from typing import List

from pydantic import BaseModel, Field


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


class ParticipantResultResponse(BaseModel):
    participant_id: int
    user_id: int
    nickname: str
    is_host: bool
    first_name: str | None
    last_name: str | None
    total_questions: int
    answered_questions: int
    correct_answers: int
    wrong_answers: int
    score: int
    finished: bool
