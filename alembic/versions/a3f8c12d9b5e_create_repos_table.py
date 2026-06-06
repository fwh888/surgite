"""create repos table

Revision ID: a3f8c12d9b5e
Revises: e5e311c2e5f0
Create Date: 2026-06-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f8c12d9b5e'
down_revision: Union[str, Sequence[str], None] = 'e5e311c2e5f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'repos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('path', sa.String(), nullable=False, unique=True),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_ingested_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('repos')