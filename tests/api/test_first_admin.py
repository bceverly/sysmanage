# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""POST /api/v1/security/first-admin: the recovery account creates the first
administrator.  Found on a fresh Ubuntu 24.04 install (2026-11-05): the
recovery account could not approve a host ("User not found") and the Users
page needed SMTP to give a new user a password."""

import pytest

from backend.auth.auth_bearer import get_current_user
from backend.main import app
from backend.persistence import models

GOOD = {
    "userid": "ops@example.com",
    "first_name": "Ops",
    "last_name": "Admin",
    "password": "Correct-Horse-9-Battery",
    "confirm_password": "Correct-Horse-9-Battery",
}


@pytest.fixture
def recovery_headers(admin_token):
    """Signed in as the recovery account, which has no database row."""
    app.dependency_overrides[get_current_user] = lambda: "admin@sysmanage.org"
    yield {"Authorization": f"Bearer {admin_token}"}
    app.dependency_overrides.pop(get_current_user, None)


def test_the_recovery_account_creates_an_administrator_with_every_role(
    client, session, recovery_headers
):
    status = client.get(
        "/api/v1/security/default-credentials-status", headers=recovery_headers
    )
    assert status.json()["needsFirstAdmin"] is True
    response = client.post(
        "/api/v1/security/first-admin", headers=recovery_headers, json=GOOD
    )
    assert response.status_code == 200, response.text
    user = session.query(models.User).filter(models.User.userid == GOOD["userid"]).one()
    assert user.is_admin and user.active
    granted = (
        session.query(models.UserSecurityRole)
        .filter(models.UserSecurityRole.user_id == user.id)
        .count()
    )
    assert granted == session.query(models.SecurityRole).count() > 0
    assert response.json()["roles"] == granted
    # Once an administrator exists the banner stops offering it ...
    status = client.get(
        "/api/v1/security/default-credentials-status", headers=recovery_headers
    )
    assert status.json()["needsFirstAdmin"] is False
    # ... and a second one is refused.
    again = client.post(
        "/api/v1/security/first-admin",
        headers=recovery_headers,
        json={**GOOD, "userid": "second@example.com"},
    )
    assert again.status_code == 409


def test_an_ordinary_user_cannot_use_it(client, session, auth_headers):
    session.add(
        models.User(userid="someone@example.com", hashed_password="x", active=True)
    )
    session.commit()
    app.dependency_overrides[get_current_user] = lambda: "someone@example.com"
    response = client.post(
        "/api/v1/security/first-admin", headers=auth_headers, json=GOOD
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "change, status",
    [
        ({"confirm_password": "Something-Else-9-Battery"}, 400),
        ({"password": "short", "confirm_password": "short"}, 400),
        ({"userid": "admin@sysmanage.org"}, 400),
    ],
)
def test_bad_input_is_refused(client, recovery_headers, change, status):
    response = client.post(
        "/api/v1/security/first-admin",
        headers=recovery_headers,
        json={**GOOD, **change},
    )
    assert response.status_code == status
