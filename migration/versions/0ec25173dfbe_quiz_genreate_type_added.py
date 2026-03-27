"""quiz_genreate_type_added

Revision ID: 0ec25173dfbe
Revises: 95679ba51014
Create Date: 2026-03-26 10:58:51.531143

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0ec25173dfbe'
down_revision = '95679ba51014'
branch_labels = None
depends_on = None

quiz_generate_type_enum = sa.Enum(
    'AI_GENERATE',
    'PDF',
    'MANUAL',
    'UNDEFINED',
    name='quiz_generate_type'
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) enum type create
    quiz_generate_type_enum.create(bind, checkfirst=True)

    # 2) column add
    op.add_column(
        'quizzes',
        sa.Column(
            'quiz_generate_type',
            quiz_generate_type_enum,
            nullable=False,
            server_default='UNDEFINED',
        )
    )

    # 3) agar defaultni keyin olib tashlamoqchi bo‘lsangiz
    op.alter_column('quizzes', 'quiz_generate_type', server_default=None)


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_column('quizzes', 'quiz_generate_type')

    # enum type faqat shu column ishlatsa, drop qilsa bo‘ladi
    quiz_generate_type_enum.drop(bind, checkfirst=True)