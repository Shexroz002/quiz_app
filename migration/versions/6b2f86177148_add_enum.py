"""add_enum

Revision ID: 6b2f86177148
Revises: d29766129f12
Create Date: 2026-03-14 14:45:02.580060

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6b2f86177148'
down_revision = 'd29766129f12'
branch_labels = None
depends_on = None


old_enum_name = "education_level"
new_enum_name = "education_level_new"

old_values = (
    "CLASS_1",
    "CLASS_2",
    "CLASS_3",
    "CLASS_4",
    "CLASS_5",
    "CLASS_6",
    "CLASS_7",
    "CLASS_8",
    "CLASS_9",
    "CLASS_10",
    "CLASS_11",
)

new_values = (
    "1-sinf",
    "2-sinf",
    "3-sinf",
    "4-sinf",
    "5-sinf",
    "6-sinf",
    "7-sinf",
    "8-sinf",
    "9-sinf",
    "10-sinf",
    "11-sinf",
)


def upgrade():
    # 1. yangi enum type yaratamiz
    op.execute(
        """
        CREATE TYPE education_level_new AS ENUM (
            '1-sinf',
            '2-sinf',
            '3-sinf',
            '4-sinf',
            '5-sinf',
            '6-sinf',
            '7-sinf',
            '8-sinf',
            '9-sinf',
            '10-sinf',
            '11-sinf'
        )
        """
    )

    # 2. ustunni text ga o'tkazamiz
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN education_level
        TYPE text
        USING education_level::text
        """
    )

    # 3. eski qiymatlarni yangisiga o'zgartiramiz
    op.execute(
        """
        UPDATE users
        SET education_level = CASE education_level
            WHEN 'CLASS_1' THEN '1-sinf'
            WHEN 'CLASS_2' THEN '2-sinf'
            WHEN 'CLASS_3' THEN '3-sinf'
            WHEN 'CLASS_4' THEN '4-sinf'
            WHEN 'CLASS_5' THEN '5-sinf'
            WHEN 'CLASS_6' THEN '6-sinf'
            WHEN 'CLASS_7' THEN '7-sinf'
            WHEN 'CLASS_8' THEN '8-sinf'
            WHEN 'CLASS_9' THEN '9-sinf'
            WHEN 'CLASS_10' THEN '10-sinf'
            WHEN 'CLASS_11' THEN '11-sinf'
            ELSE education_level
        END
        """
    )

    # 4. eski enum type ni o'chiramiz
    op.execute("DROP TYPE education_level")

    # 5. yangi type nomini eski nomga almashtiramiz
    op.execute("ALTER TYPE education_level_new RENAME TO education_level")

    # 6. ustunni yangi enum type ga o'tkazamiz
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN education_level
        TYPE education_level
        USING education_level::education_level
        """
    )


def downgrade():
    # 1. eski enumni vaqtinchalik qayta yaratamiz
    op.execute(
        """
        CREATE TYPE education_level_old AS ENUM (
            'CLASS_1',
            'CLASS_2',
            'CLASS_3',
            'CLASS_4',
            'CLASS_5',
            'CLASS_6',
            'CLASS_7',
            'CLASS_8',
            'CLASS_9',
            'CLASS_10',
            'CLASS_11'
        )
        """
    )

    # 2. ustunni text ga o'tkazamiz
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN education_level
        TYPE text
        USING education_level::text
        """
    )

    # 3. yangi qiymatlarni eski qiymatlarga qaytaramiz
    op.execute(
        """
        UPDATE users
        SET education_level = CASE education_level
            WHEN '1-sinf' THEN 'CLASS_1'
            WHEN '2-sinf' THEN 'CLASS_2'
            WHEN '3-sinf' THEN 'CLASS_3'
            WHEN '4-sinf' THEN 'CLASS_4'
            WHEN '5-sinf' THEN 'CLASS_5'
            WHEN '6-sinf' THEN 'CLASS_6'
            WHEN '7-sinf' THEN 'CLASS_7'
            WHEN '8-sinf' THEN 'CLASS_8'
            WHEN '9-sinf' THEN 'CLASS_9'
            WHEN '10-sinf' THEN 'CLASS_10'
            WHEN '11-sinf' THEN 'CLASS_11'
            ELSE education_level
        END
        """
    )

    # 4. hozirgi enum type ni o'chiramiz
    op.execute("DROP TYPE education_level")

    # 5. eski type nomini tiklaymiz
    op.execute("ALTER TYPE education_level_old RENAME TO education_level")

    # 6. ustunni eski enum type ga o'tkazamiz
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN education_level
        TYPE education_level
        USING education_level::education_level
        """
    )