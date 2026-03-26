"""add_session_status

Revision ID: 693d56965cf7
Revises: bc2054bc05e8
Create Date: 2026-03-25 15:00:04.123472

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '693d56965cf7'
down_revision = 'bc2054bc05e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    session_type_enum = postgresql.ENUM(
        'individual',
        'group',
        'public',
        name='session_type'
    )
    session_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'quiz_sessions',
        sa.Column(
            'session_type',
            session_type_enum,
            server_default='individual',
            nullable=False
        )
    )

    op.alter_column(
        'student_groups',
        'color',
        existing_type=postgresql.ENUM(
            'PURPLE', 'BLUE', 'VIOLET', 'GREEN', 'YELLOW',
            'RED', 'PINK', 'TEAL', 'ORANGE', 'CYAN',
            name='group_color'
        ),
        nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        'student_groups',
        'color',
        existing_type=postgresql.ENUM(
            'PURPLE', 'BLUE', 'VIOLET', 'GREEN', 'YELLOW',
            'RED', 'PINK', 'TEAL', 'ORANGE', 'CYAN',
            name='group_color'
        ),
        nullable=True
    )

    op.drop_column('quiz_sessions', 'session_type')

    session_type_enum = postgresql.ENUM(
        'individual',
        'group',
        'public',
        name='session_type'
    )
    session_type_enum.drop(op.get_bind(), checkfirst=True)