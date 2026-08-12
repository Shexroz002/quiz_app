from pydantic import BaseModel


class SubjectBase(BaseModel):
    id: int


class SubjectIdListSchema(SubjectBase):
    name: str|None
    type: str|None
    icon: str|None
