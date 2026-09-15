#!/usr/bin/env python3
"""Seed the EduNova database with school subjects and their ready quizzes.

Run it once after a deploy. For every subject in :data:`seed_data.SUBJECTS` it writes:

* one row in ``subjects`` (an existing subject is kept, only blank
  ``type`` / ``icon`` columns are filled in);
* one row in ``quizzes`` per quiz, with ``user_id = NULL`` so it belongs to nobody;
* the quiz's questions in ``questions``;
* four rows in ``options`` per question, exactly one of them correct.

Everything happens in one transaction, and the script is idempotent: a quiz whose
title already exists as an unassigned quiz is left untouched, so running it again
after a deploy adds only what is new and never touches quizzes that users made.
``--replace`` rewrites the seeded quizzes instead.

It needs only what the backend already installs: SQLAlchemy 2 and asyncpg.

Usage
-----
    export DATABASE_URL='postgresql+asyncpg://user:password@host:5432/quiz'
    python3 tool/seed_subjects.py              # write the missing subjects and quizzes
    python3 tool/seed_subjects.py --dry-run    # show what would be written
    python3 tool/seed_subjects.py --replace    # rewrite the quizzes that already exist
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.sql import func

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from seed_data import (  # noqa: E402  (the path above has to be set first)
    EASY,
    HARD,
    LABELS,
    MEDIUM,
    QUESTIONS_PER_QUIZ,
    SUBJECTS,
)

DIFFICULTIES = (EASY, MEDIUM, HARD)

#: The backend's ``quiz_generate_type`` enum; the script never creates it,
#: it only names it so PostgreSQL accepts the value without a cast.
QUIZ_GENERATE_TYPE = PGEnum(
    "AI_GENERATE",
    "PDF",
    "MANUAL",
    "UNDEFINED",
    name="quiz_generate_type",
    create_type=False,
)

#: These quizzes are written by hand, not generated.
GENERATE_TYPE = "MANUAL"

metadata = MetaData()

#: Only the columns this script writes; ``created_at`` / ``updated_at`` come
#: from the server defaults, so the script never has to know the time zone.
subjects_table = Table(
    "subjects",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("type", String(100)),
    Column("icon", String(25)),
)

quizzes_table = Table(
    "quizzes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(1500), nullable=False),
    Column("subject", String(255)),
    Column("description", Text),
    Column("quiz_generate_type", QUIZ_GENERATE_TYPE),
    Column("user_id", Integer),
)

questions_table = Table(
    "questions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("quiz_id", Integer, nullable=False),
    Column("question_text", Text, nullable=False),
    Column("subject", String(100)),
    Column("difficulty", String(50)),
    Column("topic", String(255)),
)

options_table = Table(
    "options",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("question_id", Integer, nullable=False),
    Column("label", String(5), nullable=False),
    Column("text", String(2000), nullable=False),
    Column("is_correct", Boolean, nullable=False),
)


def difficulty_mix(questions: list[dict]) -> dict[str, int]:
    """Count the questions per difficulty, in the order levels are declared."""
    return {level: sum(1 for item in questions if item["difficulty"] == level) for level in DIFFICULTIES}


def validate() -> None:
    """Fail before touching the database when the embedded content is malformed."""
    titles: dict[str, str] = {}
    for subject in SUBJECTS:
        name = subject["name"]
        if not subject["quizzes"]:
            raise SystemExit(f"{name}: kamida bitta test bo'lishi kerak")

        for quiz in subject["quizzes"]:
            title = quiz["title"]
            if title in titles:
                raise SystemExit(f"{name}: \"{title}\" sarlavhasi {titles[title]} da ham ishlatilgan")
            titles[title] = name

            questions = quiz["questions"]
            if len(questions) != QUESTIONS_PER_QUIZ:
                raise SystemExit(
                    f"{title}: {len(questions)} ta savol, {QUESTIONS_PER_QUIZ} ta bo'lishi kerak"
                )
            for item in questions:
                head = item["text"][:40]
                if item["difficulty"] not in DIFFICULTIES:
                    raise SystemExit(f"{title}: \"{head}\" savolining qiyinligi noma'lum")
                if len(item["options"]) != len(LABELS):
                    raise SystemExit(
                        f"{title}: \"{head}\" savolida {len(LABELS)} ta variant bo'lishi kerak"
                    )
                if len(set(item["options"])) != len(item["options"]):
                    raise SystemExit(f"{title}: \"{head}\" savolida variantlar takrorlangan")
                if not 0 <= item["answer"] < len(LABELS):
                    raise SystemExit(f"{title}: \"{head}\" savolining javob indeksi xato")


async def upsert_subject(connection: AsyncConnection, subject: dict) -> int:
    """Insert the subject when it is new, and return its id either way.

    An existing subject is never overwritten: only a missing or empty ``type``
    or ``icon`` is filled in, because those two are cosmetic and someone may
    have set them by hand.
    """
    statement = pg_insert(subjects_table).values(
        name=subject["name"],
        type=subject["type"],
        icon=subject["icon"],
    )
    statement = statement.on_conflict_do_update(
        index_elements=[subjects_table.c.name],
        set_={
            "type": func.coalesce(
                func.nullif(subjects_table.c.type, ""), statement.excluded.type
            ),
            "icon": func.coalesce(
                func.nullif(subjects_table.c.icon, ""), statement.excluded.icon
            ),
        },
    ).returning(subjects_table.c.id)
    return await connection.scalar(statement)


async def insert_quiz(connection: AsyncConnection, subject_name: str, quiz: dict) -> int:
    """Write one quiz with all of its questions and options, and return its id."""
    quiz_id = await connection.scalar(
        insert(quizzes_table)
        .values(
            title=quiz["title"],
            subject=subject_name,
            description=quiz["description"],
            quiz_generate_type=GENERATE_TYPE,
            user_id=None,  # the quiz belongs to nobody
        )
        .returning(quizzes_table.c.id)
    )

    for item in quiz["questions"]:
        question_id = await connection.scalar(
            insert(questions_table)
            .values(
                quiz_id=quiz_id,
                question_text=item["text"],
                subject=subject_name,
                difficulty=item["difficulty"],
                topic=item["topic"],
            )
            .returning(questions_table.c.id)
        )
        await connection.execute(
            insert(options_table),
            [
                {
                    "question_id": question_id,
                    "label": label,
                    "text": text,
                    "is_correct": index == item["answer"],
                }
                for index, (label, text) in enumerate(zip(LABELS, item["options"]))
            ],
        )
    return quiz_id


async def seed_quiz(
    connection: AsyncConnection, subject_name: str, quiz: dict, *, replace: bool
) -> str:
    """Seed one quiz and report what happened: ``created``, ``replaced`` or ``skipped``."""
    existing = await connection.scalar(
        select(quizzes_table.c.id).where(
            quizzes_table.c.user_id.is_(None),
            quizzes_table.c.title == quiz["title"],
        )
    )
    if existing is not None and not replace:
        return "skipped"

    action = "created"
    if existing is not None:
        # Cascades remove the questions, options and sessions of the old quiz.
        await connection.execute(delete(quizzes_table).where(quizzes_table.c.id == existing))
        action = "replaced"

    await insert_quiz(connection, subject_name, quiz)
    return action


async def seed_subject(
    connection: AsyncConnection, subject: dict, *, replace: bool
) -> list[tuple[str, str]]:
    """Seed the subject and every one of its quizzes."""
    await upsert_subject(connection, subject)
    return [
        (quiz["title"], await seed_quiz(connection, subject["name"], quiz, replace=replace))
        for quiz in subject["quizzes"]
    ]


def normalize_dsn(dsn: str) -> str:
    """Return the DSN with the asyncpg driver, whatever form the deploy uses."""
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if dsn.startswith(prefix):
            return dsn
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return "postgresql+asyncpg://" + dsn[len(prefix):]
    raise SystemExit(f"DSN tanilmadi: {dsn.split('://')[0]}://...")


async def seed(dsn: str, *, replace: bool) -> dict[str, list[tuple[str, str]]]:
    """Run the whole seed in a single transaction and return the per-subject result."""
    engine = create_async_engine(normalize_dsn(dsn), echo=False, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            return {
                subject["name"]: await seed_subject(connection, subject, replace=replace)
                for subject in SUBJECTS
            }
    finally:
        await engine.dispose()


def report(results: dict[str, list[tuple[str, str]]]) -> None:
    """Print one line per quiz plus a short summary."""
    counts: dict[str, int] = {}
    for name, quizzes in results.items():
        print(f"  {name}")
        width = max(len(title) for title, _ in quizzes)
        for title, action in quizzes:
            print(f"    {title.ljust(width)}  {action}")
            counts[action] = counts.get(action, 0) + 1
    total = sum(counts.values())
    print(f"\n  {len(results)} ta fan, {total} ta test — "
          + ", ".join(f"{action}: {count}" for action, count in sorted(counts.items())))


def preview() -> None:
    """Print the catalogue the script would write, without a database."""
    quizzes = 0
    questions = 0
    for subject in SUBJECTS:
        print(f"  {subject['name']}")
        for quiz in subject["quizzes"]:
            mix = difficulty_mix(quiz["questions"])
            quizzes += 1
            questions += len(quiz["questions"])
            print(f"    {quiz['title']} — {len(quiz['questions'])} ta savol "
                  f"({' / '.join(f'{level}: {count}' for level, count in mix.items())})")
    print(f"\n  {len(SUBJECTS)} ta fan, {quizzes} ta test, {questions} ta savol tekshirildi.")


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments, validate the content and seed the database."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL DSN; defaults to the DATABASE_URL environment variable.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Rewrite an already seeded quiz. This drops its questions and sessions.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the content and print what would be written, without a database.",
    )
    args = parser.parse_args(argv)

    validate()

    if args.dry_run:
        preview()
        return 0

    if not args.dsn:
        parser.error("DSN yo'q: DATABASE_URL muhit o'zgaruvchisini bering yoki --dsn ishlating.")

    report(asyncio.run(seed(args.dsn, replace=args.replace)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
