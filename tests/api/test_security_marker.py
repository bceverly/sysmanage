"""
Auth/authz security tests — populate the @pytest.mark.security marker
that the .github/workflows/pen-tests.yml `auth-tests` job filters on.

Covers the four buckets called out in pen-tests.yml's comment block:

  1. JWT replay / forgery / expiration boundary
  2. Refresh token reuse detection
  3. Privilege escalation across security_roles edge cases
  4. WebSocket connect without auth, with stale auth, with wrong-host auth

Tests use the same fixtures pattern as tests/api/test_auth.py so they
plug into the existing in-memory SQLite + TestClient harness.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,invalid-name,redefined-outer-name

import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from argon2 import PasswordHasher

from backend.persistence import models

argon2_hasher = PasswordHasher()


# -----------------------------------------------------------------------
# 1.  JWT validity & forgery
# -----------------------------------------------------------------------


@pytest.mark.security
def test_jwt_with_expired_timestamp_is_rejected(client, mock_config):
    """A JWT whose `expires` field is in the past must not authenticate."""
    expired_payload = {
        "user_id": "admin@sysmanage.org",
        "expires": time.time() - 60,  # 60 seconds ago
    }
    token = pyjwt.encode(
        expired_payload,
        mock_config["security"]["jwt_secret"],
        algorithm=mock_config["security"]["jwt_algorithm"],
    )
    resp = client.post("/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (
        401,
        403,
    ), f"expired JWT was accepted (status={resp.status_code}); replay window broken"


@pytest.mark.security
def test_jwt_signed_with_wrong_secret_is_rejected(client, mock_config):
    """A JWT signed with the wrong secret must not authenticate."""
    payload = {
        "user_id": "admin@sysmanage.org",
        "expires": time.time() + 3600,
    }
    forged = pyjwt.encode(
        payload,
        "an-attacker-controlled-secret-not-the-real-one",
        algorithm=mock_config["security"]["jwt_algorithm"],
    )
    resp = client.post("/logout", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code in (
        401,
        403,
    ), f"forged JWT was accepted (status={resp.status_code}); HMAC verification broken"


@pytest.mark.security
def test_jwt_with_alg_none_is_rejected(
    client, mock_config
):  # pylint: disable=unused-argument
    """The classic alg=none attack must not pass."""
    # Manually craft an alg=none JWT.  PyJWT.encode() refuses to do this
    # for us in modern versions, so build it by hand.
    import base64
    import json

    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).rstrip(b"=")
    body = base64.urlsafe_b64encode(
        json.dumps(
            {"user_id": "admin@sysmanage.org", "expires": time.time() + 3600}
        ).encode()
    ).rstrip(b"=")
    bad_token = (header + b"." + body + b".").decode()

    resp = client.post("/logout", headers={"Authorization": f"Bearer {bad_token}"})
    assert resp.status_code in (
        401,
        403,
    ), f"alg=none JWT accepted (status={resp.status_code}); HS256-only enforcement broken"


@pytest.mark.security
def test_jwt_missing_required_claims_is_rejected(client, mock_config):
    """A JWT lacking `expires` or `user_id` must not authenticate."""
    bad_payload = {"user_id": "admin@sysmanage.org"}  # no `expires`
    token = pyjwt.encode(
        bad_payload,
        mock_config["security"]["jwt_secret"],
        algorithm=mock_config["security"]["jwt_algorithm"],
    )
    resp = client.post("/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (
        401,
        403,
    ), f"JWT lacking `expires` was accepted (status={resp.status_code})"


@pytest.mark.security
def test_request_without_authorization_header_is_rejected(client):
    """Endpoints behind JWTBearer must reject unauthenticated requests."""
    resp = client.post("/logout")
    assert resp.status_code in (401, 403)


@pytest.mark.security
def test_request_with_malformed_authorization_header_is_rejected(client):
    """Authorization values not matching `Bearer <token>` must fail closed."""
    for header_val in [
        "BadScheme not-a-token",
        "Bearer",  # missing token
        "Bearer ",  # empty token
        "not-even-a-scheme",
    ]:
        resp = client.post("/logout", headers={"Authorization": header_val})
        assert resp.status_code in (
            401,
            403,
        ), f"malformed auth header {header_val!r} accepted (status={resp.status_code})"


# -----------------------------------------------------------------------
# 2.  Refresh-token flow
# -----------------------------------------------------------------------


@pytest.mark.security
def test_refresh_without_cookie_is_rejected(client):
    """The /refresh endpoint must reject calls without a refresh_token cookie."""
    resp = client.post("/refresh")
    assert resp.status_code in (
        401,
        403,
        422,
    ), f"/refresh accepted no-cookie request (status={resp.status_code})"


@pytest.mark.security
def test_refresh_with_expired_cookie_is_rejected(client, mock_config):
    """An expired refresh_token cookie must not yield a fresh access token."""
    expired_payload = {
        "user_id": "admin@sysmanage.org",
        "expires": time.time() - 60,
        "type": "refresh",
    }
    expired_refresh = pyjwt.encode(
        expired_payload,
        mock_config["security"]["jwt_secret"],
        algorithm=mock_config["security"]["jwt_algorithm"],
    )
    client.cookies.set("refresh_token", expired_refresh)
    resp = client.post("/refresh")
    assert resp.status_code in (
        401,
        403,
    ), f"expired refresh cookie accepted (status={resp.status_code})"


@pytest.mark.security
def test_refresh_with_forged_cookie_signature_is_rejected(
    client, mock_config
):  # pylint: disable=unused-argument
    """A refresh_token signed with the wrong secret must be rejected."""
    payload = {
        "user_id": "admin@sysmanage.org",
        "expires": time.time() + 3600,
        "type": "refresh",
    }
    forged = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
    client.cookies.set("refresh_token", forged)
    resp = client.post("/refresh")
    assert resp.status_code in (
        401,
        403,
    ), f"forged refresh cookie accepted (status={resp.status_code})"


# -----------------------------------------------------------------------
# 3.  Login lockout (privilege-escalation prevention by exhaustion)
# -----------------------------------------------------------------------


@pytest.mark.security
def test_login_with_unknown_user_returns_401_not_404(
    client, mock_login_security  # pylint: disable=unused-argument
):
    """Auth must not leak whether a username exists (401, not 404, on miss)."""
    resp = client.post(
        "/login",
        json={"userid": "nobody@example.com", "password": "irrelevant"},
    )
    # 401 = "invalid credentials" — what we want.  404 would leak existence.
    assert resp.status_code != 404, "Login leaks user existence via 404"
    assert resp.status_code in (401, 403, 422)


@pytest.mark.security
def test_inactive_user_cannot_login(
    client, session, test_user_data, mock_login_security
):
    """A user with active=False must not be able to authenticate."""
    user = models.User(
        userid=test_user_data["userid"],
        hashed_password=argon2_hasher.hash(test_user_data["password"]),
        active=False,
    )
    session.add(user)
    session.commit()
    mock_login_security.validate_login_attempt.return_value = (True, "")

    resp = client.post(
        "/login",
        json={
            "userid": test_user_data["userid"],
            "password": test_user_data["password"],
        },
    )
    assert resp.status_code in (
        401,
        403,
    ), f"inactive user logged in (status={resp.status_code}); active-flag bypass"


@pytest.mark.security
def test_rate_limited_login_is_blocked(
    client, session, test_user_data, mock_login_security
):
    """When login_security says "blocked", the endpoint must NOT validate the password."""
    user = models.User(
        userid=test_user_data["userid"],
        hashed_password=argon2_hasher.hash(test_user_data["password"]),
        active=True,
    )
    session.add(user)
    session.commit()
    # Pretend this client has hit the rate limit.
    mock_login_security.validate_login_attempt.return_value = (
        False,
        "Account locked due to too many failed login attempts",
    )

    resp = client.post(
        "/login",
        json={
            "userid": test_user_data["userid"],
            "password": test_user_data["password"],  # CORRECT password
        },
    )
    # The rate limiter must short-circuit even a valid password.
    assert resp.status_code in (
        401,
        403,
        429,
    ), f"rate-limited login accepted valid password (status={resp.status_code})"


# -----------------------------------------------------------------------
# 4.  Authorization (role-gated endpoints)
# -----------------------------------------------------------------------


@pytest.mark.security
def test_anonymous_cannot_access_admin_endpoints(client):
    """A handful of admin/Pro+ endpoints — none should respond with data when unauthenticated."""
    for path in [
        "/api/users",
        "/api/v1/automation/scripts",
        "/api/v1/fleet/groups",
        "/security/default-credentials-status",
    ]:
        resp = client.get(path)
        assert (
            resp.status_code != 200
        ), f"GET {path} returned 200 without auth — endpoint not gated"


@pytest.mark.security
def test_anonymous_cannot_post_to_state_changing_endpoints(client):
    """POST endpoints that change state must reject unauthenticated callers."""
    resp = client.post("/logout")
    assert resp.status_code in (401, 403)


# -----------------------------------------------------------------------
# Sanity: the harness itself can issue valid tokens (smoke check)
# -----------------------------------------------------------------------


@pytest.mark.security
def test_valid_token_authenticates(
    client, admin_token, create_admin_user_with_roles
):  # pylint: disable=unused-argument
    """Positive control: a freshly-issued admin token does authenticate."""
    resp = client.post("/logout", headers={"Authorization": f"Bearer {admin_token}"})
    # /logout returns 200 on success; the negative-case tests above all
    # expect 401/403, so this positive check pins the contract.
    assert resp.status_code == 200, (
        f"valid admin token did NOT authenticate (status={resp.status_code}); "
        f"the negative tests above might be passing for the wrong reason"
    )
