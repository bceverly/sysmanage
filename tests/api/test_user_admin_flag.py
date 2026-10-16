# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""PUT /api/v1/user/{id}/admin: making an existing user an administrator.

Only invitations could set ``is_admin`` before, so a user created any other
way could never reach the administrator-only pages (production 2026-10-16:
the only account had every role but ``is_admin = false``).  Holding EDIT_USER
is not enough to change it, and the last active administrator can be neither
demoted, deactivated nor deleted."""

import json

from backend.persistence import models

LAST_ADMIN = "last active administrator"


def _user(session, userid, is_admin=False, active=True):
    user = models.User(
        userid=userid, hashed_password="x", active=active, is_admin=is_admin
    )
    session.add(user)
    session.commit()
    return user


def _flag(session, user_id):
    session.expire_all()
    return session.query(models.User).filter(models.User.id == user_id).one().is_admin


class TestGrantAndRevoke:
    def test_an_administrator_grants_and_it_is_audited(
        self, client, session, auth_headers
    ):
        target = _user(session, "ops@example.com")
        response = client.put(
            f"/api/v1/user/{target.id}/admin",
            headers=auth_headers,
            json={"is_admin": True},
        )
        assert response.status_code == 200
        assert response.json() == {"id": str(target.id), "is_admin": True}
        assert _flag(session, target.id) is True
        audit = (
            session.query(models.AuditLog)
            .filter(models.AuditLog.entity_id == str(target.id))
            .one()
        )
        assert (audit.action_type, audit.entity_type) == ("UPDATE", "user")
        details = audit.details
        if isinstance(details, str):  # the tests' ORM mirror stores JSON as text
            details = json.loads(details)
        assert details == {"is_admin": True, "previous": False}
        assert "ops@example.com" in audit.description

    def test_an_administrator_revokes_when_another_remains(
        self, client, session, auth_headers
    ):
        target = _user(session, "ops@example.com", is_admin=True)
        response = client.put(
            f"/api/v1/user/{target.id}/admin",
            headers=auth_headers,
            json={"is_admin": False},
        )
        assert response.status_code == 200
        assert _flag(session, target.id) is False

    def test_setting_the_current_value_changes_nothing(
        self, client, session, auth_headers
    ):
        target = _user(session, "ops@example.com")
        response = client.put(
            f"/api/v1/user/{target.id}/admin",
            headers=auth_headers,
            json={"is_admin": False},
        )
        assert response.status_code == 200
        assert session.query(models.AuditLog).count() == 0

    def test_unknown_and_malformed_ids_are_404(self, client, auth_headers):
        for user_id in ("not-a-uuid", "00000000-0000-0000-0000-00000000abcd"):
            response = client.put(
                f"/api/v1/user/{user_id}/admin",
                headers=auth_headers,
                json={"is_admin": True},
            )
            assert response.status_code == 404


class TestOnlyAnAdministratorMayChangeIt:
    def test_edit_user_alone_is_refused(
        self, client, session, mock_current_user, admin_token
    ):
        # mock_current_user holds EVERY security role but is_admin=False; the
        # token only gets past JWTBearer -- the caller is mock_current_user.
        target = _user(session, "ops@example.com")
        response = client.put(
            f"/api/v1/user/{target.id}/admin",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"is_admin": True},
        )
        assert response.status_code == 403
        assert _flag(session, target.id) is False

    def test_a_user_cannot_make_themselves_administrator(
        self, client, session, mock_current_user, admin_token
    ):
        me = (
            session.query(models.User)
            .filter(models.User.userid == mock_current_user)
            .one()
        )
        response = client.put(
            f"/api/v1/user/{me.id}/admin",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"is_admin": True},
        )
        assert response.status_code == 403


class TestTheLastAdministrator:
    def _sole_admin(self, session):
        # auth_headers' admin@sysmanage.org is the recovery account AND an
        # is_admin row; make the target the only is_admin row.
        admin = (
            session.query(models.User)
            .filter(models.User.userid == "admin@sysmanage.org")
            .one()
        )
        admin.is_admin = False
        session.commit()
        return _user(session, "only-admin@example.com", is_admin=True)

    def test_cannot_be_demoted(self, client, session, auth_headers):
        target = self._sole_admin(session)
        response = client.put(
            f"/api/v1/user/{target.id}/admin",
            headers=auth_headers,
            json={"is_admin": False},
        )
        assert response.status_code == 409
        assert LAST_ADMIN in response.json()["detail"]
        assert _flag(session, target.id) is True

    def test_cannot_be_deactivated(self, client, session, auth_headers):
        target = self._sole_admin(session)
        response = client.put(
            f"/api/v1/user/{target.id}",
            headers=auth_headers,
            json={"active": False, "userid": target.userid, "password": "Xx1!xxxx"},
        )
        assert response.status_code == 409
        assert LAST_ADMIN in response.json()["detail"]

    def test_cannot_be_deleted(self, client, session, auth_headers):
        target = self._sole_admin(session)
        response = client.delete(f"/api/v1/user/{target.id}", headers=auth_headers)
        assert response.status_code == 409
        session.expire_all()
        assert (
            session.query(models.User).filter(models.User.id == target.id).count() == 1
        )

    def test_an_inactive_admin_does_not_count(self, client, session, auth_headers):
        target = self._sole_admin(session)
        _user(session, "dormant@example.com", is_admin=True, active=False)
        response = client.put(
            f"/api/v1/user/{target.id}/admin",
            headers=auth_headers,
            json={"is_admin": False},
        )
        assert response.status_code == 409


def test_the_users_list_shows_who_is_an_administrator(client, session, auth_headers):
    _user(session, "ops@example.com", is_admin=True)
    _user(session, "viewer@example.com")
    rows = {
        u["userid"]: u["is_admin"]
        for u in client.get("/api/v1/users", headers=auth_headers).json()
    }
    assert rows["ops@example.com"] is True
    assert rows["viewer@example.com"] is False
