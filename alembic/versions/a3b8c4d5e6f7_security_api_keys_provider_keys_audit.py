"""security slice: api_keys + provider_keys (encrypted) + audit_log + lockout columns

0.5.0 slice 2 (plan items #64, #71, #73). Adds:

- ``api_keys``: per-user, long-lived Bearer keys for the CLI. Key material is
  stored as an argon2id hash (matching how passwords are stored) and shown
  to the user exactly once on creation.
- ``provider_keys``: per-user, Fernet-encrypted LLM provider keys
  (``ANTHROPIC_API_KEY`` / ``GROQ_API_KEY`` / ``DEEPSEEK_API_KEY``). The
  raw key is never returned by the API; the master key is loaded from
  ``SECRETS_ENCRYPTION_KEY`` and rotated by ``scripts/rotate-secrets.sh``.
- ``audit_log``: append-only event log. ``actor_id`` is nullable so we can
  record pre-auth events like failed logins or invite redemptions. ``metadata``
  is JSONB on Postgres for indexable search; on SQLite it falls back to
  a portable ``JSON`` column.
- ``users.failed_login_count`` / ``users.locked_until`` for the lockout story
  (plan item #69). Lockout is per (email, ip) so a single user behind a
  corporate NAT doesn't lock themselves out by typo'ing on the laptop; the
  ``ip`` column lives on the audit log row so a future hardening pass can
  group by it.

Revision ID: a3b8c4d5e6f7
Revises: f5e0a0b1c2d3
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3b8c4d5e6f7"
down_revision: str | Sequence[str] | None = "f5e0a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB() if is_pg else sa.JSON()

    # --- users: lockout columns --------------------------------------------
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )

    # --- api_keys ----------------------------------------------------------
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        # Argon2id hash of the full key; we look up by the key id prefix and
        # verify the full key against this hash. SHA-256 of the full key lives
        # alongside it as a fast lookup index (argon2 is intentionally slow).
        sa.Column("prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"], unique=True)

    # --- provider_keys (Fernet-encrypted) ---------------------------------
    op.create_table(
        "provider_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        # Fernet token; the master key is the SHA-256 of
        # SECRETS_ENCRYPTION_KEY (see surgite/secrets.py). Stored as text.
        sa.Column("encrypted_key", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "provider", name="uq_provider_keys_user_provider"),
    )
    op.create_index("ix_provider_keys_user_id", "provider_keys", ["user_id"])

    # --- audit_log ---------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "actor_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("metadata", json_type, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_provider_keys_user_id", table_name="provider_keys")
    op.drop_table("provider_keys")

    op.drop_index("ix_api_keys_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
