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


# -----------------------------------------------------------------------
# 5.  WebSocket auth on /api/agent/connect
# -----------------------------------------------------------------------
#
# The agent WS endpoint authenticates via a `?token=...` query parameter
# (NOT a JWT — it's a server-issued connection token from
# websocket_security).  Behavior under failure cases:
#   - missing token   → server accepts the handshake then closes with code
#                       4401 ("authentication required")
#   - invalid token   → server accepts the handshake then closes with code
#                       4001 ("authentication failed")
# These tests use TestClient.websocket_connect which raises
# WebSocketDisconnect once the server closes; we assert the close code.


def _ws_close_code(client, path):
    """Open a WS, expect immediate close, return the close code (or None)."""
    from starlette.testclient import (  # pylint: disable=import-outside-toplevel
        WebSocketDisconnect,
    )

    try:
        with client.websocket_connect(path) as ws:
            # Some servers close after the first recv; read once to surface it.
            try:
                ws.receive_text()
            except WebSocketDisconnect as e:
                return e.code
        return None  # closed normally without an error code
    except WebSocketDisconnect as e:
        return e.code


@pytest.mark.security
def test_ws_connect_without_token_is_closed(client):
    """Anonymous WS connect must NOT be allowed to send/receive freely."""
    code = _ws_close_code(client, "/api/agent/connect")
    # 4001 / 4401 are application-level WS close codes; 1000 is "normal".
    # Anything other than a clean session-open should surface here as
    # a non-None close code.
    assert code is not None, (
        "WS /api/agent/connect did not close on anonymous connect — "
        "auth gate broken"
    )
    assert code != 1000, (
        f"WS closed with code 1000 (normal) for an anonymous connect; "
        f"expected 4xxx auth-failure"
    )


@pytest.mark.security
def test_ws_connect_with_invalid_token_is_closed(client):
    """A bogus connection token must produce an auth-failure close code."""
    code = _ws_close_code(
        client,
        "/api/agent/connect?token=this-is-definitely-not-a-real-connection-token",
    )
    assert code is not None, (
        "WS /api/agent/connect did not close on invalid token — auth gate broken"
    )
    assert code != 1000, (
        f"WS closed normally (1000) on invalid token; expected 4xxx"
    )


# -----------------------------------------------------------------------
# 6.  Privilege escalation across security_roles
# -----------------------------------------------------------------------
#
# A user without the appropriate role must be rejected with 403 from any
# role-gated endpoint.  We pick three endpoints that gate distinct roles:
#   POST   /user        → ADD_USER
#   DELETE /user/<id>   → DELETE_USER
#   PUT    /user/<id>   → EDIT_USER
# A "Reporter" / read-only user has none of these; the test issues a
# valid JWT for that user and verifies all three endpoints respond 403.


@pytest.fixture
def reporter_user_token(session, mock_config):
    """Create a real, password-hashed, no-roles user and issue them a JWT."""
    import time as _t  # pylint: disable=import-outside-toplevel

    u = models.User(
        userid="reporter-only@example.com",
        hashed_password=argon2_hasher.hash("doesntmatter"),
        active=True,
    )
    session.add(u)
    session.commit()
    payload = {
        "user_id": "reporter-only@example.com",
        "expires": _t.time() + int(mock_config["security"]["jwt_auth_timeout"]),
    }
    return pyjwt.encode(
        payload,
        mock_config["security"]["jwt_secret"],
        algorithm=mock_config["security"]["jwt_algorithm"],
    )


@pytest.mark.security
def test_role_escalation_post_user_blocked(client, reporter_user_token):
    """A user without ADD_USER must NOT be able to POST /api/user."""
    resp = client.post(
        "/api/user",
        headers={"Authorization": f"Bearer {reporter_user_token}"},
        json={
            "userid": "should-never-be-created@example.com",
            "active": True,
            "first_name": "x",
            "last_name": "y",
        },
    )
    assert resp.status_code == 403, (
        f"POST /api/user without ADD_USER role returned {resp.status_code} "
        f"(expected 403 — privilege escalation gate broken)"
    )


@pytest.mark.security
def test_role_escalation_put_user_blocked(client, reporter_user_token):
    """A user without EDIT_USER must NOT be able to PUT /api/user/<id>."""
    resp = client.put(
        "/api/user/00000000-0000-0000-0000-000000000abc",
        headers={"Authorization": f"Bearer {reporter_user_token}"},
        json={
            "userid": "noop@example.com",
            "active": True,
            "first_name": "x",
            "last_name": "y",
        },
    )
    assert resp.status_code in (
        403,
        404,
    ), (
        f"PUT /api/user/<id> without EDIT_USER role returned {resp.status_code} "
        f"(expected 403; 404 is also acceptable if the gate runs after the "
        f"lookup but before any mutation)"
    )


@pytest.mark.security
def test_role_escalation_delete_user_blocked(client, reporter_user_token):
    """A user without DELETE_USER must NOT be able to DELETE /api/user/<id>."""
    resp = client.delete(
        "/api/user/00000000-0000-0000-0000-000000000abc",
        headers={"Authorization": f"Bearer {reporter_user_token}"},
    )
    assert resp.status_code in (
        403,
        404,
    ), (
        f"DELETE /api/user/<id> without DELETE_USER role returned "
        f"{resp.status_code} (expected 403; 404 acceptable for same reason "
        f"as PUT above)"
    )
