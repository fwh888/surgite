"""invites.org_role — mark org invites and carry their membership role (1.0.0 slice 2)

Org invites (POST /orgs/{id}/members with an email) reuse the existing invite
machinery. ``org_role`` is non-null only on those: redeeming such an invite adds
the user to ``org_id`` with this role (owner|admin|member). Ordinary account
invites leave it NULL and behave exactly as before.

Additive and nullable — no backfill, no lock of note.

Revision ID: c1e5a9f3b7d2
Revises: b9d4f1a7c2e8
Create Date: 2026-07-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1e5a9f3b7d2"
down_revision: str | Sequence[str] | None = "b9d4f1a7c2e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("invites", sa.Column("org_role", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("invites", "org_role")
