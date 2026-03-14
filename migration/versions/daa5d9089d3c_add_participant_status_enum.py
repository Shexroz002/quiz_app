"""add participant status enum

Revision ID: daa5d9089d3c
Revises: 7eeb42785e11
Create Date: 2026-03-14 04:43:47.019554

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'daa5d9089d3c'
down_revision = '7eeb42785e11'
branch_labels = None
depends_on = None
participant_status_enum = sa.Enum(
    "preparing",
    "ready",
    "disconnected",
    name="participant_status_enum",
)


def upgrade():
    participant_status_enum.create(op.get_bind(), checkfirst=True)

    op.execute("""
        ALTER TABLE session_participants
        ALTER COLUMN participant_status
        TYPE participant_status_enum
        USING participant_status::participant_status_enum
    """)

    op.execute("""
        ALTER TABLE session_participants
        ALTER COLUMN participant_status
        SET DEFAULT 'preparing'
    """)

    op.execute("""
        UPDATE session_participants
        SET participant_status = 'preparing'
        WHERE participant_status IS NULL
    """)

    op.alter_column(
        "session_participants",
        "participant_status",
        nullable=False,
    )


def downgrade():
    op.execute("""
        ALTER TABLE session_participants
        ALTER COLUMN participant_status
        TYPE VARCHAR(40)
        USING participant_status::text
    """)

    participant_status_enum.drop(op.get_bind(), checkfirst=True)
