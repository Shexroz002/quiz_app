from pydantic import BaseModel


class SubjectBase(BaseModel):
    id: int


class SubjectIdListSchema(SubjectBase):
    name: str
    type: str
    icon: str
