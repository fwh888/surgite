"""unique repo name + commits FK cascade

Add UNIQUE constraint on repos.name to prevent name collisions.
Add commits.repo_id FK to repos.id with ON DELETE CASCADE so deleting
a repo automatically removes its commits. Rebuild the (repo, date)
index on (repo_id, date).

Revision ID: b2c3d4e5f6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-11

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_repos_name", "repos", ["name"])

    op.add_column("commits", sa.Column("repo_id", sa.Integer(), nullable=True))

    op.execute("UPDATE commits SET repo_id = repos.id FROM repos WHERE commits.repo = repos.name")

    op.alter_column("commits", "repo_id", nullable=False)

    op.create_foreign_key(
        "fk_commits_repo_id",
        "commits",
        "repos",
        ["repo_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_index("ix_commits_repo_date", table_name="commits")
    op.create_index("ix_commits_repo_date", "commits", ["repo_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_commits_repo_date", table_name="commits")
    op.create_index("ix_commits_repo_date", "commits", ["repo", "date"])

    op.drop_constraint("fk_commits_repo_id", "commits", type_="foreignkey")
    op.drop_column("commits", "repo_id")

    op.drop_constraint("uq_repos_name", "repos", type_="unique")
