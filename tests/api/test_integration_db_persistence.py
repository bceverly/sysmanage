"""
End-to-end persistence-layer integration tests.

Exercises the SQLAlchemy session + model layer the rest of the API
sits on top of.  These run against the in-memory SQLite the test
fixtures spin up locally and against real Postgres in the CI
`integration-server` job — same code paths, different driver, so
this catches "works on SQLite, breaks on Postgres" regressions.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,invalid-name

from datetime import datetime, timezone

import pytest
from argon2 import PasswordHasher

from backend.persistence import models

argon2_hasher = PasswordHasher()


@pytest.mark.integration
def test_user_round_trip(session):
    """Insert a User, query it back, verify all required fields persist."""
    u = models.User(
        userid="round-trip@example.com",
        hashed_password=argon2_hasher.hash("anything"),
        active=True,
    )
    session.add(u)
    session.commit()

    fetched = (
        session.query(models.User)
        .filter(models.User.userid == "round-trip@example.com")
        .first()
    )
    assert fetched is not None
    assert fetched.userid == "round-trip@example.com"
    assert fetched.active is True


@pytest.mark.integration
def test_user_unique_constraint_on_userid(session):
    """Two users with the same userid must not be insertable."""
    u1 = models.User(
        userid="dup@example.com",
        hashed_password=argon2_hasher.hash("a"),
        active=True,
    )
    session.add(u1)
    session.commit()

    u2 = models.User(
        userid="dup@example.com",
        hashed_password=argon2_hasher.hash("b"),
        active=True,
    )
    session.add(u2)
    with pytest.raises(Exception):  # pylint: disable=broad-exception-caught
        session.commit()
    session.rollback()


@pytest.mark.integration
def test_user_last_access_update_persists(session):
    """Updating last_access on a User must persist across a refresh."""
    u = models.User(
        userid="last-access@example.com",
        hashed_password=argon2_hasher.hash("a"),
        active=True,
    )
    session.add(u)
    session.commit()
    user_id = u.id

    new_time = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    u.last_access = new_time
    session.commit()

    session.expire_all()
    refreshed = session.get(models.User, user_id)
    # Datetime equality across the round-trip can lose sub-second precision
    # depending on the driver.  Compare to the second.
    assert refreshed.last_access is not None
    assert refreshed.last_access.replace(microsecond=0) == new_time


@pytest.mark.integration
def test_inactive_user_persists_active_false(session):
    """active=False must round-trip correctly (auth flow depends on this — see test_security_marker)."""
    u = models.User(
        userid="inactive@example.com",
        hashed_password=argon2_hasher.hash("a"),
        active=False,
    )
    session.add(u)
    session.commit()

    fetched = (
        session.query(models.User)
        .filter(models.User.userid == "inactive@example.com")
        .first()
    )
    assert fetched is not None
    assert fetched.active is False, (
        "active=False did not round-trip; the inactive-user-cannot-login security "
        "test now depends on this column actually persisting"
    )
