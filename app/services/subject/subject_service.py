from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.repositories.subject.subject_repo import SubjectRepository
from app.services.base import BaseService


class SubjectService(BaseService):

    def __init__(self, db: AsyncSession):
        super().__init__(SubjectRepository(db))



def get_subject_service(db: AsyncSession = Depends(get_db)) -> SubjectService:
    return SubjectService(db)