from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from app.repositories.quiz.quiz_repo import (
    QuizRepository,
    editable_quiz_condition,
    visible_quiz_condition,
)
from app.schemas.quiz.quiz import QuizListSchema, QuizUpdateSchema


def sql(clause):
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class VisibleQuizConditionTests(TestCase):
    """O'z testlari + ro'yxatdan o'tishda tanlangan fanlar bo'yicha umumiy katalog."""

    def setUp(self):
        self.sql = sql(visible_quiz_condition(7))

    def test_a_students_own_quizzes_stay_visible(self):
        self.assertIn("quizzes.user_id = 7", self.sql)

    def test_the_catalogue_is_narrowed_to_the_picked_subjects(self):
        self.assertIn("quizzes.user_id IS NULL", self.sql)
        self.assertIn("lower(trim(quizzes.subject)) IN", self.sql)
        self.assertIn("lower(trim(subjects.name))", self.sql)
        self.assertIn("user_subject.user_id = 7", self.sql)

    def test_the_subject_filter_only_applies_to_the_catalogue_branch(self):
        # or_(own, and_(no owner, picked subject)) -- ownerless quizzes must never
        # arrive on their own, otherwise every student sees the whole catalogue.
        own, catalogue = visible_quiz_condition(7).clauses
        self.assertIn("quizzes.user_id = 7", sql(own))
        self.assertEqual(len(catalogue.clauses), 2)
        self.assertIn("IS NULL", sql(catalogue))
        self.assertIn("user_subject", sql(catalogue))


class OwnerOnlyLookupTests(IsolatedAsyncioTestCase):
    """Katalog testini tahrirlash yoki o'chirish hammaga ta'sir qiladi."""

    def _repo(self):
        statements = []

        async def execute(stmt):
            statements.append(stmt)
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        return QuizRepository(SimpleNamespace(execute=execute)), statements

    async def test_update_looks_the_quiz_up_by_owner(self):
        repo, statements = self._repo()

        self.assertIsNone(await repo.update(3, 7, {"title": "Yangi"}))
        self.assertNotIn("IS NULL", sql(statements[0]))

    async def test_delete_looks_the_quiz_up_by_owner(self):
        repo, statements = self._repo()

        self.assertIsNone(await repo.delete(3, 7))
        self.assertNotIn("IS NULL", sql(statements[0]))

    async def test_reading_a_quiz_follows_the_shared_visibility(self):
        repo, statements = self._repo()

        await repo.get(3, 7)
        self.assertIn("user_subject", sql(statements[0]))


class BotCatalogPageTests(IsolatedAsyncioTestCase):
    """Bot katalogi ham aynan shu ro'yxatni ko'rsatishi kerak."""

    async def _page(self):
        from app.bot.handlers import menu

        statements = []

        async def execute(stmt):
            statements.append(stmt)
            return SimpleNamespace(
                scalar_one=lambda: 3,
                mappings=lambda: SimpleNamespace(all=lambda: []),
            )

        with patch("app.bot.handlers.menu.AsyncSessionLocal") as factory:
            factory.return_value.__aenter__ = AsyncMock(
                return_value=SimpleNamespace(execute=execute)
            )
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await menu.get_quiz_catalog_page(1, 7)
        return statements

    async def test_both_the_count_and_the_page_use_the_shared_condition(self):
        statements = await self._page()

        self.assertEqual(len(statements), 2)
        for statement in statements:
            self.assertIn("user_subject.user_id = 7", sql(statement))
            self.assertIn("quizzes.user_id IS NULL", sql(statement))


class EditableFlagTests(TestCase):
    """`is_update` ro'yxatdagi har bir testga: uni tahrirlash mumkinmi."""

    def setUp(self):
        self.sql = sql(editable_quiz_condition(7))

    def test_the_owner_may_edit(self):
        self.assertIn("quizzes.user_id = 7", self.sql)

    def test_an_ownerless_quiz_is_ruled_out_explicitly(self):
        # `NULL = 7` bu NULL, false emas -- shuning uchun alohida shart kerak,
        # aks holda katalog qatorlari uchun bayroq null bo'lib qaytadi.
        self.assertIn("quizzes.user_id IS NOT NULL", self.sql)

    def test_the_flag_matches_what_the_put_allows(self):
        # `get_owned` ham aynan shu shartni qo'llaydi: ro'yxatda tugma
        # ko'rinsa, PUT ham o'tishi kerak.
        self.assertEqual(sql(editable_quiz_condition(7)).count("user_id"), 2)

    def test_the_schema_defaults_to_not_editable(self):
        row = {
            "created_at": "2026-09-16T10:00:00",
            "quiz_id": 1,
            "title": "Test",
            "quiz_generate_type": "MANUAL",
        }
        # Bayroq yetishmasa, tugma ko'rsatilmaydi -- xavfsiz tomon.
        self.assertFalse(QuizListSchema(**row).is_update)


class UpdatePayloadTests(TestCase):
    """Yuborilmagan maydon o'chirilmasligi kerak."""

    def test_only_the_sent_fields_are_written(self):
        data = QuizUpdateSchema(title="Yangi nom", quiz_generate_type="MANUAL")
        dumped = data.model_dump(exclude_unset=True)

        # To'liq dump `subject`/`description` ni None qilib yozardi va
        # sarlavhani tahrirlash ularni jimgina o'chirib yuborardi.
        self.assertEqual(set(dumped), {"title", "quiz_generate_type"})
        self.assertIn("subject", data.model_dump())
