"""orgs + org_members tables and org_id partitioning (1.0.0 slice 1)

The multi-tenant foundation. Adds the two org tables, a ``personal_org_id`` FK
on ``users``, and a nullable ``org_id`` FK to the nine per-user tables. Then
backfills: one *personal* org per existing user (slug derived from the email
local-part, disambiguated with a numeric suffix on collision), an ``owner``
membership row, and ``org_id`` on every per-user row resolved through the
owning user's personal org.

The API surface is unchanged by this migration — every existing endpoint keeps
resolving to the user's personal org (see ``backend/scope.py``). Only the schema
moves. ``commits`` is intentionally left out: a commit's org is derivable via
``repo_id -> repos.org_id``.

Single transaction (alembic's default). Targets Postgres, like the other
migrations here; the test suite builds its schema from the ORM metadata, not
from this file. The slug rule is re-implemented inline (kept trivial) rather
than importing ``backend.auth.slugify_org``, so the migration never depends on
the app's current models.

Revision ID: b9d4f1a7c2e8
Revises: g1b2c3d4e5f6
Create Date: 2026-07-01

"""

import re
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b9d4f1a7c2e8"
down_revision: str | Sequence[str] | None = "g1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Nine per-user tables gain org_id, grouped by which column points at the owning
# user. `commits` is excluded (derivable via repo_id -> repos.org_id).
_ORG_BY_OWNER = ("repos", "prompt_settings", "shared_summaries")  # keyed on owner_id
_ORG_BY_USER = ("sessions", "api_keys", "provider_keys", "password_resets")  # keyed on user_id
# invites -> created_by, audit_log -> actor_id (both nullable — NULL keys stay org-less)
_ORG_BY_NULLABLE = (("invites", "created_by"), ("audit_log", "actor_id"))
_ALL_ORG_TABLES = (
    *_ORG_BY_OWNER,
    *_ORG_BY_USER,
    *(t for t, _ in _ORG_BY_NULLABLE),
)
# Drop NOT NULL here: these resources become org-ownable (owner_id NULL) in slice 2.
_OWNER_NULLABLE = ("repos", "prompt_settings", "shared_summaries")


def _slug(local_part: str) -> str:
    """Email local-part -> URL-safe slug base (mirror of auth.slugify_org)."""
    s = re.sub(r"[^a-z0-9]+", "-", local_part.lower()).strip("-")[:32].strip("-")
    if len(s) < 3:
        s = f"{s}-org" if s else "org"
    return s


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "orgs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orgs_slug", "orgs", ["slug"], unique=True)

    op.create_table(
        "org_members",
        sa.Column(
            "org_id",
            sa.String(),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.add_column("users", sa.Column("personal_org_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_users_personal_org_id_orgs",
        "users",
        "orgs",
        ["personal_org_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- Backfill: one personal org + owner membership per existing user. ---
    users = list(bind.execute(sa.text("SELECT id, email, display_name FROM users")))
    used_slugs: set[str] = set()
    for u in users:
        base = _slug((u.email or "org").split("@")[0])
        slug, n = base, 1
        while slug in used_slugs:
            n += 1
            slug = f"{base}-{n}"
        used_slugs.add(slug)
        org_id = str(uuid.uuid4())
        bind.execute(
            sa.text("INSERT INTO orgs (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": org_id, "name": u.display_name or base, "slug": slug},
        )
        bind.execute(
            sa.text("INSERT INTO org_members (org_id, user_id, role) VALUES (:oid, :uid, 'owner')"),
            {"oid": org_id, "uid": u.id},
        )
        bind.execute(
            sa.text("UPDATE users SET personal_org_id = :oid WHERE id = :uid"),
            {"oid": org_id, "uid": u.id},
        )

    # --- org_id column + FK on every per-user table, then backfill. ---
    for table in _ALL_ORG_TABLES:
        op.add_column(table, sa.Column("org_id", sa.String(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_org_id_orgs", table, "orgs", ["org_id"], ["id"], ondelete="SET NULL"
        )

    for table in _ORG_BY_OWNER:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET org_id = "  # noqa: S608 — table names are a fixed literal set
                "(SELECT personal_org_id FROM users WHERE users.id = "
                f"{table}.owner_id)"
            )
        )
    for table in _ORG_BY_USER:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET org_id = "  # noqa: S608
                "(SELECT personal_org_id FROM users WHERE users.id = "
                f"{table}.user_id)"
            )
        )
    for table, key in _ORG_BY_NULLABLE:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET org_id = "  # noqa: S608
                f"(SELECT personal_org_id FROM users WHERE users.id = {table}.{key}) "
                f"WHERE {key} IS NOT NULL"
            )
        )

    # --- owner_id becomes nullable where org ownership is coming in slice 2. ---
    for table in _OWNER_NULLABLE:
        op.alter_column(table, "owner_id", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    for table in _OWNER_NULLABLE:
        op.alter_column(table, "owner_id", existing_type=sa.String(), nullable=False)

    for table in _ALL_ORG_TABLES:
        op.drop_constraint(f"fk_{table}_org_id_orgs", table, type_="foreignkey")
        op.drop_column(table, "org_id")

    op.drop_constraint("fk_users_personal_org_id_orgs", "users", type_="foreignkey")
    op.drop_column("users", "personal_org_id")

    op.drop_table("org_members")
    op.drop_index("ix_orgs_slug", table_name="orgs")
    op.drop_table("orgs")
