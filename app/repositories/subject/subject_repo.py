from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subject
from app.repositories.base.base_repository import BaseRepository


class SubjectRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(Subject, db)