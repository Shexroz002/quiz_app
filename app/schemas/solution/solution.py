from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SolveSubject = Literal["matematika", "fizika"]


class SolutionQuota(BaseModel):
    """How many problems the student can still bring in today."""

    limit: int
    used: int
    left: int
    resets_at: datetime


class ExplanationResponse(BaseModel):
    """A bank question's solution, or why there is none yet.

    ``pending`` means it is being written; the client asks again shortly.
    ``unavailable`` means there will not be one, and ``message`` says why.
    ``disputed`` means two independent solutions agreed on ``model_option``
    while the key says ``correct_option``; the key is probably wrong.
    """

    status: Literal["ready", "pending", "unavailable", "disputed"]
    explanation_id: int | None = None
    #: The question as the student saw it, so a solution screen can open
    #: from a link without the test in memory.
    question_text: str | None = None
    correct_option: str | None = None
    model_option: str | None = None
    #: True when the student picked the option the solutions agreed on.
    student_may_be_right: bool = False
    solution: dict | None = None
    #: How the student's own wrong option probably came about, when known.
    hint: dict | None = None
    message: str | None = None


class RecognizeResponse(BaseModel):
    request_id: int
    readable: bool
    text: str
    subject: SolveSubject
    multiple: bool
    image_url: str | None = None
    quota: SolutionQuota


class SolveCreate(BaseModel):
    """A problem to solve: the confirmed text of a photo, or typed text."""

    request_id: int | None = None
    text: str = Field(min_length=5, max_length=4000)
    subject: SolveSubject


class SolveRequestResponse(BaseModel):
    id: int
    status: Literal["recognized", "pending", "done", "failed"]
    subject: str
    text: str
    image_url: str | None = None
    solution: dict | None = None
    #: Shown to the student when the problem could not be solved.
    message: str | None = None
    #: True when it failed for lack of the model, so asking again may work and
    #: costs nothing; false when the problem itself was incomplete.
    retryable: bool = False
    created_at: datetime


class SolveHistoryItem(BaseModel):
    id: int
    status: Literal["recognized", "pending", "done", "failed"]
    subject: str
    text: str
    created_at: datetime


class FeedbackCreate(BaseModel):
    explanation_id: int | None = None
    solve_request_id: int | None = None
    verdict: Literal["helpful", "unclear", "wrong"]
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _one_target(self) -> "FeedbackCreate":
        if (self.explanation_id is None) == (self.solve_request_id is None):
            raise ValueError("explanation_id yoki solve_request_id dan aynan bittasi kerak")
        return self


class FeedbackResponse(BaseModel):
    verdict: Literal["helpful", "unclear", "wrong"]
