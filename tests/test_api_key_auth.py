"""
Unit tests for API-key authentication helpers (Phase 13.2).

Covers key generation/hashing/shape detection and the database-backed
``authenticate_api_key`` resolver, including the rejection paths (revoked,
expired, inactive user, unknown key, non-key credential).
"""

import uuid
from datetime import datetime, timedelta, timezone

from backend.auth.api_key import (
    API_KEY_PREFIX,
    authenticate_api_key,
    generate_api_key,
    hash_api_key,
    looks_like_api_key,
)
from backend.persistence.models import ApiKey, User


def _naive_utc(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class TestApiKeyHelpers:
    """Pure helpers — no database."""

    def test_generate_shape(self):
        full, key_hash, prefix = generate_api_key()
        assert full.startswith(API_KEY_PREFIX)
        assert len(key_hash) == 64  # sha256 hex
        assert prefix == full[:12]
        assert hash_api_key(full) == key_hash

    def test_generate_unique(self):
        a, _, _ = generate_api_key()
        b, _, _ = generate_api_key()
        assert a != b

    def test_looks_like_api_key(self):
        full, _, _ = generate_api_key()
        assert looks_like_api_key(full) is True
        assert looks_like_api_key("eyJhbGciOi.JzdWIi.signature") is False
        assert looks_like_api_key("") is False
        assert looks_like_api_key(None) is False


def _make_user(db_session, active=True, locked=False):
    user = User(
        userid=f"key-user-{uuid.uuid4()}@example.com",
        hashed_password="x",
        active=active,
        is_admin=False,
        is_locked=locked,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_key(db_session, user, *, expires_at=None, is_active=True, revoked_at=None):
    full, key_hash, prefix = generate_api_key()
    key = ApiKey(
        user_id=user.id,
        name="test",
        key_prefix=prefix,
        key_hash=key_hash,
        is_active=is_active,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )
    db_session.add(key)
    db_session.commit()
    return full


class TestAuthenticateApiKey:
    """DB-backed resolver against the in-memory test engine."""

    def test_valid_key_resolves_user(self, db_session):
        user = _make_user(db_session)
        full = _make_key(db_session, user)
        principal = authenticate_api_key(full)
        assert principal is not None
        assert principal["user_id"] == user.userid
        assert principal["tenant_id"] is None

    def test_unknown_key_returns_none(self, db_session):
        _make_user(db_session)
        full, _, _ = generate_api_key()  # never persisted
        assert authenticate_api_key(full) is None

    def test_non_api_key_credential_returns_none(self, db_session):
        assert authenticate_api_key("eyJ.not.akey") is None

    def test_revoked_key_returns_none(self, db_session):
        user = _make_user(db_session)
        full = _make_key(
            db_session,
            user,
            is_active=False,
            revoked_at=_naive_utc(datetime.now(timezone.utc)),
        )
        assert authenticate_api_key(full) is None

    def test_expired_key_returns_none(self, db_session):
        user = _make_user(db_session)
        past = _naive_utc(datetime.now(timezone.utc) - timedelta(hours=1))
        full = _make_key(db_session, user, expires_at=past)
        assert authenticate_api_key(full) is None

    def test_future_expiry_still_valid(self, db_session):
        user = _make_user(db_session)
        future = _naive_utc(datetime.now(timezone.utc) + timedelta(hours=1))
        full = _make_key(db_session, user, expires_at=future)
        assert authenticate_api_key(full) is not None

    def test_inactive_user_returns_none(self, db_session):
        user = _make_user(db_session, active=False)
        full = _make_key(db_session, user)
        assert authenticate_api_key(full) is None

    def test_locked_user_returns_none(self, db_session):
        user = _make_user(db_session, locked=True)
        full = _make_key(db_session, user)
        assert authenticate_api_key(full) is None

    def test_last_used_at_is_stamped(self, db_session):
        user = _make_user(db_session)
        full = _make_key(db_session, user)
        assert authenticate_api_key(full) is not None
        key = db_session.query(ApiKey).filter(ApiKey.user_id == user.id).first()
        db_session.refresh(key)
        assert key.last_used_at is not None
