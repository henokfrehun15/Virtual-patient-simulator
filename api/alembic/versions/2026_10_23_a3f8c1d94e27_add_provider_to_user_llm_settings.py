"""add provider to user llm settings

Revision ID: a3f8c1d94e27
Revises: d272f0b8b2cd
Create Date: 2026-10-23 10:12:41.310924

"""

from alembic import op
import sqlalchemy as sa


revision = 'a3f8c1d94e27'
down_revision = 'd272f0b8b2cd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_llm_settings',
        sa.Column('provider', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_llm_settings', 'provider')
