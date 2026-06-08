"""create prompt_settings table

Stores user-configurable AI prompt settings as a singleton row (id=1).
Settings are editable via the web UI and used by the summarizer when
generating standup summaries.

Revision ID: d6b8f37e2c4a
Revises: c5a9e26f1d3a
Create Date: 2026-06-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6b8f37e2c4a"
down_revision: str | Sequence[str] | None = "c5a9e26f1d3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_name", sa.String(), nullable=False, server_default=""),
        sa.Column("user_role", sa.String(), nullable=False, server_default=""),
        sa.Column("tone", sa.String(), nullable=False, server_default="neutral"),
        sa.Column("group_count", sa.String(), nullable=False, server_default="2-5"),
        sa.Column("output_format", sa.String(), nullable=False, server_default="markdown"),
        sa.Column("custom_instructions", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("prompt_settings")
