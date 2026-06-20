"""password reset tokens (issue #77)

Adds a ``password_resets`` table for admin-minted one-time reset tokens.
The token format is ``pr_<id>_<secret>``; we store the argon2id hash of
the full token plus the ``id`` (8 chars) as a fast lookup index, exactly
mirroring the ``api_keys`` design from slice 2.

Revision ID: g1b2c3d4e5f6
Revises: a3b8c4d5e6f7
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "g1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "a3b8c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])
    op.create_index("ix_password_resets_expires_at", "password_resets", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_password_resets_expires_at", table_name="password_resets")
    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_table("password_resets")
