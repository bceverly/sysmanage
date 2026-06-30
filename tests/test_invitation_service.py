"""Tests for backend/services/invitation_service.py (Phase 13.3).

Uses the root ``db_session`` fixture (full ``Base`` schema — the
``tests/api`` curated ``TestBase`` does not include ``user_invitation``).
"""

from datetime import timedelta

import pytest

from backend.persistence import models
from backend.services import invitation_service as svc


def _make_role(db_session, name):
    group = models.SecurityRoleGroup(name=f"grp-{name}")
    db_session.add(group)
    db_session.flush()
    role = models.SecurityRole(name=name, group_id=group.id)
    db_session.add(role)
    db_session.flush()
    return role


# --------------------------------------------------------------------------- #
# create_invitation
# --------------------------------------------------------------------------- #
def test_create_invitation_basic(db_session):
    inv = svc.create_invitation(db_session, email="new@example.com", invited_by="admin")
    db_session.commit()
    assert inv.email == "new@example.com"
    assert inv.token
    assert inv.invited_by == "admin"
    assert inv.is_pending() is True
    assert inv.accepted_at is None and inv.revoked_at is None


def test_create_invitation_rejects_existing_user(db_session):
    db_session.add(models.User(userid="taken@example.com", active=True))
    db_session.commit()
    with pytest.raises(svc.InvitationError):
        svc.create_invitation(db_session, email="taken@example.com", invited_by="admin")


def test_create_invitation_validates_roles(db_session):
    with pytest.raises(svc.InvitationError):
        svc.create_invitation(
            db_session,
            email="x@example.com",
            invited_by="admin",
            role_ids=["00000000-0000-0000-0000-000000000000"],
        )


def test_create_invitation_with_valid_role(db_session):
    role = _make_role(db_session, "Add User")
    inv = svc.create_invitation(
        db_session, email="x@example.com", invited_by="admin", role_ids=[str(role.id)]
    )
    db_session.commit()
    assert list(inv.role_ids) == [str(role.id)]


def test_create_invitation_supersedes_prior_pending(db_session):
    first = svc.create_invitation(
        db_session, email="dup@example.com", invited_by="admin"
    )
    db_session.commit()
    first_id = first.id
    second = svc.create_invitation(
        db_session, email="dup@example.com", invited_by="admin"
    )
    db_session.commit()
    assert svc.get_invitation(db_session, first_id).is_pending() is False  # revoked
    assert second.is_pending() is True


# --------------------------------------------------------------------------- #
# list / revoke / validate
# --------------------------------------------------------------------------- #
def test_list_and_pending_only(db_session):
    a = svc.create_invitation(db_session, email="a@example.com", invited_by="x")
    b = svc.create_invitation(db_session, email="b@example.com", invited_by="x")
    db_session.commit()
    svc.revoke_invitation(db_session, a.id)
    db_session.commit()
    all_rows = svc.list_invitations(db_session)
    pending = svc.list_invitations(db_session, pending_only=True)
    assert {r.email for r in all_rows} >= {"a@example.com", "b@example.com"}
    assert "a@example.com" not in {r.email for r in pending}
    assert "b@example.com" in {r.email for r in pending}


def test_revoke_then_token_invalid(db_session):
    inv = svc.create_invitation(db_session, email="r@example.com", invited_by="x")
    db_session.commit()
    assert svc.get_valid_invitation(db_session, inv.token) is not None
    assert svc.revoke_invitation(db_session, inv.id) is True
    db_session.commit()
    assert svc.get_valid_invitation(db_session, inv.token) is None
    # revoking again is a no-op
    assert svc.revoke_invitation(db_session, inv.id) is False


def test_expired_token_invalid(db_session):
    inv = svc.create_invitation(db_session, email="e@example.com", invited_by="x")
    inv.expires_at = svc._now() - timedelta(hours=1)
    db_session.commit()
    assert svc.get_valid_invitation(db_session, inv.token) is None


# --------------------------------------------------------------------------- #
# accept_invitation
# --------------------------------------------------------------------------- #
def test_accept_creates_user_with_roles(db_session):
    role = _make_role(db_session, "Add User")
    inv = svc.create_invitation(
        db_session,
        email="join@example.com",
        invited_by="admin",
        role_ids=[str(role.id)],
        is_admin=True,
        first_name="Jo",
    )
    db_session.commit()

    user = svc.accept_invitation(db_session, token=inv.token, password="hunter2pass")
    db_session.commit()

    assert user.userid == "join@example.com"
    assert user.active is True
    assert user.is_admin is True
    assert user.first_name == "Jo"
    assert user.hashed_password and user.hashed_password != "hunter2pass"
    links = (
        db_session.query(models.UserSecurityRole)
        .filter(models.UserSecurityRole.user_id == user.id)
        .all()
    )
    assert {str(link.role_id) for link in links} == {str(role.id)}
    # token is single-use now
    assert svc.get_valid_invitation(db_session, inv.token) is None


def test_accept_invalid_token(db_session):
    with pytest.raises(svc.InvitationError):
        svc.accept_invitation(db_session, token="nope", password="hunter2pass")


def test_accept_when_user_already_exists(db_session):
    inv = svc.create_invitation(db_session, email="race@example.com", invited_by="x")
    db_session.commit()
    db_session.add(models.User(userid="race@example.com", active=True))
    db_session.commit()
    with pytest.raises(svc.InvitationError):
        svc.accept_invitation(db_session, token=inv.token, password="hunter2pass")
