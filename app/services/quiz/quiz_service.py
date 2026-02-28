import logging
import re

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.models.quiz import Quiz, Question, Option, QuestionImage
from app.repositories.quiz.quiz_repo import QuizRepository
from app.services.pdf.pdf_service import PDFService
from app.websocket.notification_manager import notification_manager


class QuizService:

    def __init__(self, db: AsyncSession):
        self.repo = QuizRepository(db)

    async def list(self, user_id: int):
        return await self.repo.list(user_id)

    async def get(self, quiz_id: int, user_id: int):
        return await self.repo.get(quiz_id, user_id)

    async def update(self, quiz_id: int, user_id: int, update_data: dict):
        return await self.repo.update(quiz_id, user_id, update_data)

    async def delete(self, quiz_id: int, user_id: int):
        return await self.repo.delete(quiz_id, user_id)

    async def quiz_answer_list(self, quiz_id: int):
        def conver_list_do_dict(lst):
            return {item['id']: item['label'] for item in lst}
        return conver_list_do_dict(await self.repo.quiz_answer_by_id(quiz_id))


def get_quiz_service(db: AsyncSession = Depends(get_db)) -> QuizService:
    return QuizService(db)


async def save_quiz_from_json(db: AsyncSession, data: dict, pdf_path: str,user_id:int) -> int:
    try:
        quiz = Quiz(title=data["quiz_title"], user_id=user_id)
        db.add(quiz)
        await db.flush()
        pdf_server = PDFService()
        pdf_images = await pdf_server.extract_images(pdf_path)
        for q in data["questions"]:
            question = Question(
                quiz_id=quiz.id,
                question_text=q["question"],
                subject=q.get("subject"),
                table_markdown=q.get("table_markdown"),
                difficulty=q.get("meta", {}).get("difficulty"),
                topic=q.get("meta", {}).get("topic"),
            )
            db.add(question)
            await db.flush()

            for img_url in q.get("images", []):
                img_url = re.sub(r"[\[\]\"]", "", img_url)
                db.add(
                    QuestionImage(
                        question_id=question.id,
                        image_url=pdf_images.get(img_url) or 'http://localhost:8000/'
                    )
                )

            # ---------- options ----------
            for opt in q.get("options", []):
                db.add(
                    Option(
                        question_id=question.id,
                        label=opt["id"],
                        text=opt["text"],
                        is_correct=opt["is_correct"],
                    )
                )

        await db.commit()

        # Send notification to user about quiz creation via websocket

        return quiz.id
    except Exception as e:
        await db.rollback()
        logging.exception("Failed to save quiz from JSON with data: %s", e)

