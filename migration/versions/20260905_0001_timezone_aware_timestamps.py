"""Make timestamp columns timezone-aware.

Revision ID: 20260905_0001
Revises:
Create Date: 2026-09-05
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET TIME ZONE 'UTC'")
    op.alter_column(
        "attempt_answers",
        "answered_at",
        existing_type=sa.TIMESTAMP(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="answered_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "session_participants",
        "joined_at",
        existing_type=sa.TIMESTAMP(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="joined_at AT TIME ZONE 'Asia/Tashkent'",
    )
    op.alter_column(
        "chats",
        "last_message_created_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="last_message_created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chat_members",
        "joined_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="joined_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "users",
        "date_of_birth",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="date_of_birth AT TIME ZONE 'Asia/Tashkent'",
    )
    op.alter_column(
        "users",
        "last_login",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="last_login AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.execute("SET TIME ZONE 'UTC'")
    op.alter_column(
        "users",
        "last_login",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=True,
        postgresql_using="last_login AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "users",
        "date_of_birth",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=True,
        postgresql_using="date_of_birth AT TIME ZONE 'Asia/Tashkent'",
    )
    op.alter_column(
        "chat_members",
        "joined_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=False,
        postgresql_using="joined_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chats",
        "last_message_created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=True,
        postgresql_using="last_message_created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "session_participants",
        "joined_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=False,
        postgresql_using="joined_at AT TIME ZONE 'Asia/Tashkent'",
    )
    op.alter_column(
        "attempt_answers",
        "answered_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=False,
        postgresql_using="answered_at AT TIME ZONE 'UTC'",
    )
