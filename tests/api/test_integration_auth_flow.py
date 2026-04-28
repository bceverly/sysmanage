"""
End-to-end auth flow tests.

Exercises the full login → authed-request → logout cycle through the
real router stack with the test database.  Differs from the unit tests
in tests/api/test_auth.py:  those mock individual layers; these run
the cycle through real components and verify the issued JWT is then
accepted by a real protected endpoint.

Tagged @pytest.mark.integration so they populate the integration-server
job in .github/workflows/integration-tests.yml.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,invalid-name,redefined-outer-name

import pytest
from argon2 import PasswordHasher

from backend.persistence import models

argon2_hasher = PasswordHasher()


@pytest.fixture
def db_user(session, test_user_data):
    """Create an active database user for the auth-flow tests."""
    user = models.User(
        userid=test_user_data["userid"],
        hashed_password=argon2_hasher.hash(test_user_data["password"]),
        active=True,
    )
    session.add(user)
    session.commit()
    return user


@pytest.mark.integration
def test_login_issues_usable_jwt(
    client,
    db_user,
    test_user_data,
    mock_login_security,  # pylint: disable=unused-argument
):
    """A successful POST /login must return an Authorization JWT that
    actually works on a protected endpoint."""
    mock_login_security.validate_login_attempt.return_value = (True, "")

    resp = client.post(
        "/login",
        json={
            "userid": test_user_data["userid"],
            "password": test_user_data["password"],
        },
    )
    assert resp.status_code == 200
    token = resp.json().get("Authorization")
    assert token, f"login response had no Authorization field: {resp.json()}"

    # Now use that token on /logout (the simplest JWT-gated endpoint).
    logout_resp = client.post("/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200, (
        f"freshly-issued JWT was not accepted by /logout (status="
        f"{logout_resp.status_code}); auth wiring broken"
    )


@pytest.mark.integration
def test_login_then_use_health_endpoint_unauth(client):
    """Health endpoint is unauthenticated and works whether or not we've logged in."""
    pre = client.get("/api/health")
    assert pre.status_code == 200

    # Even without logging in (no Authorization header), still 200.
    post = client.get("/api/health")
    assert post.status_code == 200


@pytest.mark.integration
def test_logout_without_auth_rejected(client):
    """The /logout endpoint must reject anonymous calls."""
    resp = client.post("/logout")
    assert resp.status_code in (401, 403)


@pytest.mark.integration
def test_failed_login_records_audit_attempt(
    client,
    db_user,
    test_user_data,
    mock_login_security,  # pylint: disable=unused-argument
):
    """A wrong-password login must call record_failed_login and return 401."""
    mock_login_security.validate_login_attempt.return_value = (True, "")

    resp = client.post(
        "/login",
        json={
            "userid": test_user_data["userid"],
            "password": "definitely-not-the-right-password",
        },
    )
    assert resp.status_code == 401
    assert mock_login_security.record_failed_login.called, (
        "wrong-password login did NOT call record_failed_login; "
        "rate-limit signal will be missed"
    )


@pytest.mark.integration
def test_login_unknown_user_does_not_distinguish_from_wrong_password(
    client, mock_login_security
):
    """Unknown userid must produce the same 401 as wrong-password —
    no user-existence enumeration via response shape."""
    mock_login_security.validate_login_attempt.return_value = (True, "")

    resp = client.post(
        "/login",
        json={
            "userid": "no-such-user@example.com",
            "password": "anything",
        },
    )
    assert (
        resp.status_code == 401
    ), f"unknown user got {resp.status_code}; should be 401 like wrong-password"
    # Body should be the same generic message.
    body = resp.json()
    assert "Invalid username or password" in body.get(
        "detail", ""
    ), f"unknown-user response leaks via different message: {body!r}"
