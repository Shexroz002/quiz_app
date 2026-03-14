"""add_new

Revision ID: d29766129f12
Revises: daa5d9089d3c
Create Date: 2026-03-14 04:52:46.161231

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd29766129f12'
down_revision = 'daa5d9089d3c'
branch_labels = None
depends_on = None

participant_status_enum = sa.Enum(
    "preparing",
    "ready",
    "disconnected",
    name="participant_status_enum"
)


def upgrade():
    # ENUM type yaratish
    participant_status_enum.create(op.get_bind(), checkfirst=True)

    # column type ni enumga o'tkazish
    op.execute("""
        ALTER TABLE session_participants
        ALTER COLUMN participant_status
        TYPE participant_status_enum
        USING participant_status::participant_status_enum
    """)

    # default qo'yish
    op.execute("""
        ALTER TABLE session_participants
        ALTER COLUMN participant_status
        SET DEFAULT 'preparing'
    """)

    # agar null qiymatlar bo'lsa
    op.execute("""
        UPDATE session_participants
        SET participant_status = 'preparing'
        WHERE participant_status IS NULL
    """)

    op.alter_column(
        "session_participants",
        "participant_status",
        nullable=False
    )


def downgrade():
    op.execute("""
        ALTER TABLE session_participants
        ALTER COLUMN participant_status
        TYPE VARCHAR(40)
        USING participant_status::text
    """)

    participant_status_enum.drop(op.get_bind(), checkfirst=True)