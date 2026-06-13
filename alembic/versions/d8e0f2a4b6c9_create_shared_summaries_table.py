"""create shared_summaries table

Backs the shareable-summary-link feature: a slug maps to the stored summary
query params (repo, range, author, ai settings). Resolving the slug re-runs
the query. Rows expire (default 7 days) and are swept by the background
scheduler; the read path also rejects expired slugs.

Revision ID: d8e0f2a4b6c9
Revises: c7d9e1f3a5b8
Create Date: 2026-06-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8e0f2a4b6c9"
down_revision: str | Sequence[str] | None = "c7d9e1f3a5b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shared_summaries",
        sa.Column("slug", sa.String(), primary_key=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_shared_summaries_expires_at", "shared_summaries", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_shared_summaries_expires_at", table_name="shared_summaries")
    op.drop_table("shared_summaries")
