# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Sticky last-selected-tenant behavior (``User.last_tenant_id``).

Covers ``_default_tenant_id_for_user`` (select-on-login: prefer a valid stored
tenant, else default/first grant, and keep the sticky current) plus the
``_get_user_last_tenant`` / ``_set_user_last_tenant`` read/write helpers.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.api.auth as auth
from backend.persistence import models


def _grant(tenant_id, is_default=False):
    return SimpleNamespace(tenant_id=tenant_id, is_default=is_default)


def _run_default_tenant(stored, grants, active_grant=True):
    """Invoke _default_tenant_id_for_user with the registry + sticky I/O mocked;
    returns (result, set_mock)."""
    with patch.object(
        auth.config, "is_multitenancy_enabled", return_value=True
    ), patch.object(auth, "_open_registry_session", return_value=MagicMock()), patch(
        "backend.services.registry_service.resolve_registry_user_id",
        return_value="ruid",
    ), patch(
        "backend.services.registry_service.list_user_grants", return_value=grants
    ), patch(
        "backend.services.registry_service.has_active_grant",
        return_value=active_grant,
    ), patch.object(
        auth, "_get_user_last_tenant", return_value=stored
    ), patch.object(
        auth, "_set_user_last_tenant"
    ) as set_mock:
        result = auth._default_tenant_id_for_user("u@example.com")
    return result, set_mock


def test_none_when_multitenancy_disabled():
    with patch.object(auth.config, "is_multitenancy_enabled", return_value=False):
        assert auth._default_tenant_id_for_user("u@example.com") is None


def test_prefers_valid_stored_tenant_over_default():
    result, set_mock = _run_default_tenant(
        stored="t-stored",
        grants=[_grant("t-default", is_default=True), _grant("t-stored")],
        active_grant=True,
    )
    assert result == "t-stored"  # sticky wins over is_default
    set_mock.assert_not_called()  # already current -> no write


def test_populates_sticky_when_null():
    result, set_mock = _run_default_tenant(
        stored=None,
        grants=[_grant("t-default", is_default=True), _grant("t-other")],
    )
    assert result == "t-default"  # is_default grant
    set_mock.assert_called_once_with("u@example.com", "t-default")


def test_heals_stale_stored_tenant():
    # stored tenant is no longer a live grant -> fall back + rewrite the sticky
    result, set_mock = _run_default_tenant(
        stored="t-revoked",
        grants=[_grant("t-default", is_default=True)],
        active_grant=False,
    )
    assert result == "t-default"
    set_mock.assert_called_once_with("u@example.com", "t-default")


def test_falls_back_to_first_grant_without_default():
    result, set_mock = _run_default_tenant(
        stored=None,
        grants=[_grant("t-first"), _grant("t-second")],
    )
    assert result == "t-first"
    set_mock.assert_called_once_with("u@example.com", "t-first")


def test_none_when_no_grants():
    result, set_mock = _run_default_tenant(stored=None, grants=[])
    assert result is None
    set_mock.assert_not_called()


def test_get_set_last_tenant_roundtrip():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    maker = sessionmaker(bind=engine)
    s = maker()
    s.add(models.User(userid="u@example.com", active=True, hashed_password="x"))
    s.commit()
    s.close()

    tid = "11111111-1111-1111-1111-111111111111"  # tenant ids are UUIDs
    with patch.object(auth.db, "get_engine", return_value=engine):
        assert auth._get_user_last_tenant("u@example.com") is None
        auth._set_user_last_tenant("u@example.com", tid)
        assert auth._get_user_last_tenant("u@example.com") == tid
        # unknown user -> no row, best-effort no-op (never raises)
        auth._set_user_last_tenant(
            "missing@example.com", "22222222-2222-2222-2222-222222222222"
        )
        assert auth._get_user_last_tenant("missing@example.com") is None
    engine.dispose()
