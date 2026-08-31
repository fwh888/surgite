"""Effective org scope resolution (1.0.0 slice 1).

Every request runs in the context of one *org*. Slice 1 is single-org: a user's
current org is always their personal org, so `resolve_scope` just reads
`user.personal_org_id`. Slice 2 adds the active-org cookie and
`POST /orgs/{id}/switch`, at which point `current_org_id` diverges from
`personal_org_id` — the seam is here so no endpoint has to change again.

Route handlers take `scope: EffectiveScope = Depends(resolve_scope)` and set
`org_id=scope.current_org_id` on inserts. Non-request call sites (the plain
functions in `surgite.auth`) use `auth.personal_org_id(session, user_id)`
instead, since they have no `Request` to hang a dependency on.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from surgite.auth import create_personal_org, get_current_user
from surgite.db import OrgMemberRow, OrgRow, UserRow, get_db


@dataclass(frozen=True)
class EffectiveScope:
    user_id: str
    personal_org_id: str
    current_org_id: str
    current_org_role: str


def resolve_scope(
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EffectiveScope:
    """FastAPI dependency: the caller's effective org scope. In slice 1 the
    current org is always the personal org (no switch cookie yet)."""
    personal = user.personal_org_id
    if personal is None:
        # Self-heal data that predates the org backfill so downstream inserts
        # never write a NULL org_id. A no-op after the 1.0.0 migration.
        personal = create_personal_org(session, user).id
    return EffectiveScope(
        user_id=user.id,
        personal_org_id=personal,
        current_org_id=personal,
        current_org_role="owner",
    )


def assert_org_member(org_id: str, session: Session, user: UserRow) -> OrgMemberRow:
    """Guard for org-scoped routes (used for real by slice 2's /orgs/{id}/*):
    404 if the org is missing or soft-deleted, 403 if the caller isn't a
    member. Returns the membership row so the handler can check the role."""
    org = session.get(OrgRow, org_id)
    if org is None or org.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Org not found")
    member = session.get(OrgMemberRow, (org_id, user.id))
    if member is None:
        raise HTTPException(status_code=403, detail="Not a member of this org")
    return member
