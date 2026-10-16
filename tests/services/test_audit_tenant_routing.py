# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Audit rows are per tenant (2026-10-16).

Production had a tenant's actions split across two databases (24 audit rows
in bootstrap, 24 in the tenant) because callers picked the session.  The rule
``AuditService.log`` now enforces:
  * a tenant event handed a bootstrap session while a tenant is active is
    written to that tenant's database;
  * server events (logins, users, security roles, tenants, settings) always
    go to bootstrap;
  * a session already on a tenant database is never moved (background ticks);
  * single-tenant deployments are untouched."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services.audit_service import (
    ActionType,
    AuditService,
    EntityType,
    Result,
)


def _engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[models.AuditLog.__table__])
    return engine


@pytest.fixture
def engines():
    bootstrap, tenant = _engine(), _engine()
    yield bootstrap, tenant
    bootstrap.dispose()
    tenant.dispose()


@contextmanager
def _deployment(bootstrap, tenant, multitenant=True, active=True):
    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=multitenant
    ), patch("backend.persistence.db.get_engine", return_value=bootstrap), patch(
        "backend.persistence.partitions.get_request_engine",
        return_value=tenant if active else bootstrap,
    ):
        yield


def _log(session, action=ActionType.EXECUTE, entity=EntityType.HOST, **kw):
    return AuditService.log(
        db=session,
        action_type=action,
        entity_type=entity,
        description="x",
        result=Result.SUCCESS,
        **kw,
    )


def _rows(engine):
    with sessionmaker(bind=engine)() as session:
        return session.query(models.AuditLog).count()


def test_a_tenant_event_on_a_bootstrap_session_lands_in_the_tenant(engines):
    bootstrap, tenant = engines
    with _deployment(bootstrap, tenant), sessionmaker(bind=bootstrap)() as main:
        entry = _log(main)
        main.commit()
    assert (_rows(bootstrap), _rows(tenant)) == (0, 1)
    assert entry.id is not None  # still usable by the caller


@pytest.mark.parametrize(
    "action,entity",
    [
        (ActionType.LOGIN, EntityType.AUTHENTICATION),
        (ActionType.LOGIN_FAILED, EntityType.HOST),
        (ActionType.UPDATE, EntityType.USER),
        (ActionType.PERMISSION_CHANGE, EntityType.SECURITY_ROLE),
        (ActionType.CREATE, EntityType.TENANT),
        (ActionType.UPDATE, EntityType.SETTING),
    ],
)
def test_server_events_stay_in_bootstrap_even_from_a_tenant_session(
    engines, action, entity
):
    bootstrap, tenant = engines
    with _deployment(bootstrap, tenant), sessionmaker(bind=tenant)() as tsession:
        _log(tsession, action=action, entity=entity)
        tsession.commit()
    assert (_rows(bootstrap), _rows(tenant)) == (1, 0)


def test_a_tenant_session_is_never_moved(engines):
    """Background ticks pass the tenant database they are reconciling and
    bind no active tenant: that session is the right answer."""
    bootstrap, tenant = engines
    with _deployment(bootstrap, tenant, active=False), sessionmaker(
        bind=tenant
    )() as tsession:
        _log(tsession, commit=False)
        tsession.commit()
    assert (_rows(bootstrap), _rows(tenant)) == (0, 1)


def test_server_scope_writes_bootstrap(engines):
    bootstrap, tenant = engines
    with _deployment(bootstrap, tenant, active=False), sessionmaker(
        bind=bootstrap
    )() as main:
        _log(main)
    assert (_rows(bootstrap), _rows(tenant)) == (1, 0)


def test_single_tenant_is_untouched(engines):
    bootstrap, tenant = engines
    with _deployment(bootstrap, tenant, multitenant=False), sessionmaker(
        bind=bootstrap
    )() as main:
        _log(main)
    assert (_rows(bootstrap), _rows(tenant)) == (1, 0)


def test_test_doubles_are_written_to_as_given():
    db = MagicMock()
    with patch("backend.config.config.is_multitenancy_enabled", return_value=True):
        _log(db)
    db.add.assert_called_once()
    db.commit.assert_called_once()
