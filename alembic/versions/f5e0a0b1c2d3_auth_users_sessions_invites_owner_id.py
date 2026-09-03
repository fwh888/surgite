"""auth foundation: users / sessions / invites tables + owner_id partitioning

Added in 0.5.0. Creates the three auth tables and adds a non-nullable
``owner_id`` FK to every pre-existing table.

Data migration: a single bootstrap user (BOOTSTRAP_OWNER_EMAIL, default
``owner@localhost``) is created and every existing repo / commit /
prompt_settings / shared_summary row is re-associated with it, so a 0.4.0
database upgrades in place with all its data owned by the operator. The
operator then sets that user's password via ``scripts/upgrade-from-0.4.sh``
(or redeems the bootstrap invite on a greenfield install).

``email`` is CITEXT on Postgres for index-supported case-insensitive lookups;
on any other backend it degrades to a plain String (the app lower-cases on the
way in so the two behave the same).

For a large 0.4.0 dataset, create the ``owner_id`` indexes CONCURRENTLY before
running this migration (see docs/migrations/0.4.0-to-0.5.0.md) so the
ALTER ... SET NOT NULL doesn't hold a long lock; on a small dataset the plain
index created here is fine.

Revision ID: f5e0a0b1c2d3
Revises: d8e0f2a4b6c9
Create Date: 2026-06-19

"""

import os
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f5e0a0b1c2d3"
down_revision: str | Sequence[str] | None = "d8e0f2a4b6c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OWNED_TABLES = ("repos", "commits", "prompt_settings", "shared_summaries")


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    email_type: sa.types.TypeEngine = postgresql.CITEXT() if is_pg else sa.String()
    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", email_type, nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "invites",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column(
            "created_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "used_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index("ix_invites_token", "invites", ["token"], unique=True)

    # Bootstrap owner: created with no password (set later by the operator via
    # scripts/upgrade-from-0.4.sh or by redeeming the bootstrap invite).
    bootstrap_email = os.environ.get("BOOTSTRAP_OWNER_EMAIL", "owner@localhost").strip().lower()
    bootstrap_id = str(uuid.uuid4())
    users_t = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("email", sa.String),
        sa.column("display_name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_admin", sa.Boolean),
    )
    op.bulk_insert(
        users_t,
        [
            {
                "id": bootstrap_id,
                "email": bootstrap_email,
                "display_name": "owner",
                "is_active": True,
                "is_admin": True,
            }
        ],
    )

    # owner_id on every existing table: add nullable, backfill to the bootstrap
    # user, then enforce NOT NULL.
    for table in _OWNED_TABLES:
        op.add_column(table, sa.Column("owner_id", sa.String(), nullable=True))
        bind.execute(
            sa.text(f"UPDATE {table} SET owner_id = :oid"),
            {"oid": bootstrap_id},  # noqa: S608
        )
        op.alter_column(table, "owner_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_owner_id_users", table, "users", ["owner_id"], ["id"], ondelete="CASCADE"
        )
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])

    # prompt_settings uniqueness becomes per (owner, repo).
    op.drop_constraint("uq_prompt_settings_repo_id", "prompt_settings", type_="unique")
    op.create_unique_constraint(
        "uq_prompt_settings_owner_repo", "prompt_settings", ["owner_id", "repo_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_prompt_settings_owner_repo", "prompt_settings", type_="unique")
    op.create_unique_constraint("uq_prompt_settings_repo_id", "prompt_settings", ["repo_id"])

    for table in _OWNED_TABLES:
        op.drop_index(f"ix_{table}_owner_id", table_name=table)
        op.drop_constraint(f"fk_{table}_owner_id_users", table, type_="foreignkey")
        op.drop_column(table, "owner_id")

    op.drop_index("ix_invites_token", table_name="invites")
    op.drop_table("invites")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
