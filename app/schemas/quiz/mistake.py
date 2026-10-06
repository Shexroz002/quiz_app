from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MistakeSubjectSchema(BaseModel):
    """One subject's share of the bank."""

    subject: str
    total: int = Field(description="Open questions in this subject")
    due: int = Field(description="How many of them are ready today")
    next_due_at: datetime | None = Field(
        default=None, description="When the next one returns, if none is due now"
    )


class MistakeOverviewSchema(BaseModel):
    """What the bank screen shows before a review starts."""

    total: int = Field(description="Open questions, all subjects")
    due: int = Field(description="Ready to review right now")
    next_due_at: datetime | None = None
    cleared_last_30_days: int = 0
    subjects: list[MistakeSubjectSchema] = []


class MistakeOptionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    text: str


class MistakeQuestionSchema(BaseModel):
    """A question served for review.

    The correct option is included: a review is practice, not a test, so the
    answer is revealed as soon as the student has chosen (owner decision).
    """

    question_id: int
    question_text: str
    subject: str | None = None
    topic: str | None = None
    table_markdown: str | None = None
    image_urls: list[str] = []
    options: list[MistakeOptionSchema] = []
    correct_option: str | None = None
    wrong_count: int = Field(description="How many times the student has missed it")


class MistakeAnswerRequest(BaseModel):
    selected_option: str = Field(max_length=5)


class MistakeAnswerResponse(BaseModel):
    """What one answer did to the schedule."""

    question_id: int
    is_correct: bool
    correct_option: str | None = None
    streak: int = Field(description="Correct answers in a row, 0..2")
    cleared: bool = Field(description="True when the question left the bank")
    next_due_at: datetime | None = Field(
        default=None, description="None once the question is cleared"
    )
    remaining_due: int = Field(description="Still waiting in this review")
