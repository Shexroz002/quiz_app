from pathlib import Path

from fastapi import Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.models.quiz import Question
from app.repositories.quiz.question_repo import QuestionRepository


class QuestionService:

    def __init__(self, db: AsyncSession):
        self.repo = QuestionRepository(db)
        self.db = db

    async def detail(self, question_id: int, user_id: int) -> Question:
        return await self.repo.detail(question_id, user_id)

    async def upload_image_to_question(self, question_id: int, user_id: int, image: UploadFile) -> Question:
        base_dir = Path("media/image") / str(question_id)
        base_dir.mkdir(parents=True, exist_ok=True)

        file_path = base_dir / image.filename

        content = await image.read()

        with open(file_path, "wb") as buffer:
            buffer.write(content)

        image_url = f"/media/image/{question_id}/{image.filename}"

        upload_image = await self.repo.upload_image_to_question(
            question_id,
            user_id,
            image_url,
        )

        await self.db.commit()
        return upload_image

    async def delete_question_image(self, question_id: int, user_id: int, image_id: int) -> None:
        deleted_image = await self.repo.delete_question_image(question_id, user_id, image_id)
        await self.db.commit()
        return deleted_image

    async def update_correct_option(self, question_id: int, user_id: int, option_id: int) -> Question:
        updated_question = await self.repo.update_correct_option(question_id, user_id, option_id)
        await self.db.commit()
        return updated_question


def get_question_service(db: AsyncSession = Depends(get_db)) -> QuestionService:
    return QuestionService(db)
