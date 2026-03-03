from pydantic import BaseModel

class OptionBase(BaseModel):
    label: str
    text: str
    is_correct: bool


class OptionWithoutCorrect(BaseModel):
    label: str
    text: str