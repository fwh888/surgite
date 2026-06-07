"""add clone_url to repos

Revision ID: b4f7d13e8a2c
Revises: a3f8c12d9b5e
Create Date: 2026-06-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4f7d13e8a2c"
down_revision: str | Sequence[str] | None = "a3f8c12d9b5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repos", sa.Column("clone_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("repos", "clone_url")
