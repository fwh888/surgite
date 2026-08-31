"""Org data-model tests (1.0.0 slice 1).

Slice 1 is invisible from the API, so these exercise the primitives directly:
the slug rule, `create_personal_org` (idempotency + slug disambiguation), the
`resolve_scope` dependency's logic, and the `assert_org_member` guard.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from surgite.auth import create_personal_org, create_user, slugify_org
from surgite.db import OrgMemberRow, OrgRow, UserRow, get_session
from surgite.scope import assert_org_member, resolve_scope


def test_slugify_rules():
    assert slugify_org("alice") == "alice"
    assert slugify_org("Alice.Smith") == "alice-smith"
    assert slugify_org("a+b@weird") == "a-b-weird"
    # Too short is padded to >= 3 chars; empty falls back to "org".
    assert slugify_org("a") == "a-org"
    assert slugify_org("!!") == "org"
    # Trimmed to 32 chars, no leading/trailing dashes.
    assert slugify_org("x" * 50) == "x" * 32
    assert len(slugify_org("x" * 50)) <= 32


def test_create_user_gets_personal_org():
    with get_session() as s:
        user = create_user(s, email="dana@example.com", password="pw-correct-horse")
        assert user.personal_org_id is not None
        org = s.get(OrgRow, user.personal_org_id)
        assert org is not None and org.slug == "dana"
        member = s.get(OrgMemberRow, (org.id, user.id))
        assert member is not None and member.role == "owner"


def test_create_personal_org_is_idempotent():
    with get_session() as s:
        user = create_user(s, email="e@example.com", password="pw-correct-horse")
        first = user.personal_org_id
        again = create_personal_org(s, user)  # already has one -> no new org
        assert again.id == first
        assert s.scalar(select(OrgMemberRow).where(OrgMemberRow.user_id == user.id)) is not None
        assert len(s.scalars(select(OrgRow).where(OrgRow.slug.like("e%"))).all()) == 1


def test_personal_org_slug_disambiguated_on_collision():
    with get_session() as s:
        u1 = create_user(s, email="sam@a.example.com", password="pw-correct-horse")
        u2 = create_user(s, email="sam@b.example.com", password="pw-correct-horse")
        o1 = s.get(OrgRow, u1.personal_org_id)
        o2 = s.get(OrgRow, u2.personal_org_id)
        assert {o1.slug, o2.slug} == {"sam", "sam-2"}


def test_resolve_scope_returns_personal_org():
    with get_session() as s:
        user = create_user(s, email="fran@example.com", password="pw-correct-horse")
        scope = resolve_scope(user=user, session=s)
        assert scope.user_id == user.id
        assert scope.personal_org_id == user.personal_org_id
        assert scope.current_org_id == user.personal_org_id
        assert scope.current_org_role == "owner"


def test_resolve_scope_self_heals_missing_personal_org():
    with get_session() as s:
        # A user created directly (bypassing create_user) has no personal org.
        user = UserRow(email="ghost@example.com", display_name="ghost")
        s.add(user)
        s.commit()
        s.refresh(user)
        assert user.personal_org_id is None
        scope = resolve_scope(user=user, session=s)
        assert scope.current_org_id is not None
        assert user.personal_org_id == scope.current_org_id


def test_assert_org_member_ok_and_guards():
    with get_session() as s:
        member = create_user(s, email="in@example.com", password="pw-correct-horse")
        outsider = create_user(s, email="out@example.com", password="pw-correct-horse")
        org_id = member.personal_org_id

        row = assert_org_member(org_id, s, member)
        assert row.role == "owner"

        with pytest.raises(HTTPException) as missing:
            assert_org_member("no-such-org", s, member)
        assert missing.value.status_code == 404

        with pytest.raises(HTTPException) as forbidden:
            assert_org_member(org_id, s, outsider)
        assert forbidden.value.status_code == 403
