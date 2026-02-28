from pydantic import BaseModel


class SubjectIdListSchema(BaseModel):
    id: int
