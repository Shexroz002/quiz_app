from pydantic import BaseModel


class SubmitAnswerRequest(BaseModel):
    question_id: int
    selected_option: str


class SubmitAnswerResponse(BaseModel):
    question_id: int
    selected_option: str


class FinishQuizResponse(BaseModel):
    session_id: int
    attempt_id: int
    total_questions: int
    answered_questions: int
    correct_answers: int
    wrong_answers: int
    score: int
    finished: bool


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
