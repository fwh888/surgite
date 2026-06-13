"""per-repo prompt settings

Drop the singleton (id=1) prompt-settings pattern: add a nullable repo_id FK
so each repo can carry its own prompt overrides, with the existing global row
left as repo_id IS NULL. A unique constraint keeps a repo to one row; the
single global row is maintained in application code (a partial unique index on
NULL isn't portable).

Revision ID: c7d9e1f3a5b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7d9e1f3a5b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New column is nullable, so the existing global row keeps repo_id = NULL —
    # exactly the backfill we want (it becomes the global default).
    op.add_column("prompt_settings", sa.Column("repo_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_prompt_settings_repo_id",
        "prompt_settings",
        "repos",
        ["repo_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_prompt_settings_repo_id", "prompt_settings", ["repo_id"])


def downgrade() -> None:
    op.drop_constraint("uq_prompt_settings_repo_id", "prompt_settings", type_="unique")
    op.drop_constraint("fk_prompt_settings_repo_id", "prompt_settings", type_="foreignkey")
    op.drop_column("prompt_settings", "repo_id")
