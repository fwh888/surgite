"""date column type and indexes

Change commits.date from String to Date for native date operations and better
indexing. Add indexes on date, (repo, date), and author to support the query
patterns in _query_commits.

Revision ID: f1a2b3c4d5e6
Revises: d6b8f37e2c4a
Create Date: 2026-06-10

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d6b8f37e2c4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "commits",
        "date",
        type_=sa.Date(),
        existing_type=sa.String(),
        existing_nullable=False,
        postgresql_using="date::date",
    )
    op.create_index("ix_commits_date", "commits", ["date"])
    op.create_index("ix_commits_repo_date", "commits", ["repo", "date"])
    op.create_index("ix_commits_author", "commits", ["author"])


def downgrade() -> None:
    op.drop_index("ix_commits_author", table_name="commits")
    op.drop_index("ix_commits_repo_date", table_name="commits")
    op.drop_index("ix_commits_date", table_name="commits")
    op.alter_column(
        "commits",
        "date",
        type_=sa.String(),
        existing_type=sa.Date(),
        existing_nullable=False,
    )
