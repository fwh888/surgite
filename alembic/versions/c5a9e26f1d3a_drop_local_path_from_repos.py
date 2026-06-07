"""drop local path from repos

Local-path repos are no longer supported: in a containerised deployment the
checked-out repos never live on the host, so a repo is always a remote clone
URL. Drop the `path` column and promote `clone_url` to the required, unique key.

Revision ID: c5a9e26f1d3a
Revises: b4f7d13e8a2c
Create Date: 2026-06-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5a9e26f1d3a'
down_revision: Union[str, Sequence[str], None] = 'b4f7d13e8a2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Local-path repos (no clone_url) can no longer be ingested; drop them
    # before tightening the column to NOT NULL.
    op.execute("DELETE FROM repos WHERE clone_url IS NULL")
    op.drop_column('repos', 'path')
    op.alter_column('repos', 'clone_url', existing_type=sa.String(), nullable=False)
    op.create_unique_constraint('uq_repos_clone_url', 'repos', ['clone_url'])


def downgrade() -> None:
    op.drop_constraint('uq_repos_clone_url', 'repos', type_='unique')
    op.alter_column('repos', 'clone_url', existing_type=sa.String(), nullable=True)
    # `path` was originally NOT NULL/unique, but we have no values to backfill,
    # so restore it as nullable.
    op.add_column('repos', sa.Column('path', sa.String(), nullable=True))
