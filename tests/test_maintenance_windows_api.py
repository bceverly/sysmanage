# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for backend/api/maintenance_windows.py (Phase 14.2).

Validation (400s), admin gating (403), a create→list→update→delete round-trip and
the audited emergency override — all against the in-memory test engine.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api import maintenance_windows as mod
from backend.api.maintenance_windows import (
    MaintenanceWindowIn,
    OverrideIn,
    ScopeIn,
    _validate_window,
    create_maintenance_window,
    create_override,
    delete_maintenance_window,
    list_maintenance_windows,
    update_maintenance_window,
)
from backend.persistence.models import AuditLog


def _admin():
    user = MagicMock()
    user.is_admin = True
    user.id = uuid.uuid4()
    user.userid = "admin@example.com"
    return user


def _daily(**kw):
    base = dict(
        name="Nightly",
        kind="allow",
        recurrence="daily",
        timezone="UTC",
        start_time="02:00",
        duration_minutes=120,
        scopes=[ScopeIn(scope_type="all")],
    )
    base.update(kw)
    return MaintenanceWindowIn(**base)


@pytest.fixture
def patched_sm(engine, monkeypatch):
    """Bind the API's _sessionmaker to the in-memory test engine."""
    monkeypatch.setattr(mod, "_sessionmaker", lambda: sessionmaker(bind=engine))
    return engine


class TestValidation:
    def test_bad_kind(self):
        with pytest.raises(HTTPException) as exc:
            _validate_window(_daily(kind="nope"))
        assert exc.value.status_code == 400

    def test_bad_recurrence(self):
        with pytest.raises(HTTPException) as exc:
            _validate_window(_daily(recurrence="hourly"))
        assert exc.value.status_code == 400

    def test_unknown_timezone(self):
        with pytest.raises(HTTPException) as exc:
            _validate_window(_daily(timezone="Mars/Olympus"))
        assert exc.value.status_code == 400

    def test_no_scopes(self):
        with pytest.raises(HTTPException) as exc:
            _validate_window(_daily(scopes=[]))
        assert exc.value.status_code == 400

    def test_recurring_needs_time_and_duration(self):
        with pytest.raises(HTTPException):
            _validate_window(_daily(start_time=None))
        with pytest.raises(HTTPException):
            _validate_window(_daily(duration_minutes=0))

    def test_weekly_needs_days(self):
        with pytest.raises(HTTPException) as exc:
            _validate_window(_daily(recurrence="weekly", days_of_week=[]))
        assert exc.value.status_code == 400

    def test_once_needs_ordered_bounds(self):
        from datetime import datetime, timedelta

        now = datetime(2026, 7, 11, 12, 0)
        with pytest.raises(HTTPException):
            _validate_window(
                _daily(
                    recurrence="once",
                    start_time=None,
                    duration_minutes=None,
                    starts_at=now,
                    ends_at=now - timedelta(hours=1),  # end before start
                )
            )

    def test_host_scope_needs_host_id(self):
        with pytest.raises(HTTPException):
            _validate_window(_daily(scopes=[ScopeIn(scope_type="host")]))


@pytest.mark.asyncio
async def test_non_admin_is_forbidden(patched_sm):
    user = MagicMock()
    user.is_admin = False
    with pytest.raises(HTTPException) as exc:
        await list_maintenance_windows(current_user=user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_list_update_delete_roundtrip(patched_sm):
    admin = _admin()

    created = await create_maintenance_window(_daily(), current_user=admin)
    assert created["name"] == "Nightly"
    assert created["scopes"][0]["scope_type"] == "all"
    window_id = created["id"]

    listed = await list_maintenance_windows(current_user=admin)
    assert len(listed["windows"]) == 1

    # Update: switch to a weekly window scoped to a specific host.
    host_id = str(uuid.uuid4())
    updated = await update_maintenance_window(
        window_id,
        _daily(
            name="Weekly",
            recurrence="weekly",
            start_time="03:00",
            duration_minutes=60,
            days_of_week=["mon", "wed"],
            scopes=[ScopeIn(scope_type="host", host_id=host_id)],
        ),
        current_user=admin,
    )
    assert updated["name"] == "Weekly"
    assert updated["recurrence"] == "weekly"
    assert set(updated["days_of_week"]) == {"mon", "wed"}
    assert updated["scopes"][0]["host_id"] == host_id

    deleted = await delete_maintenance_window(window_id, current_user=admin)
    assert deleted["status"] == "deleted"
    assert (await list_maintenance_windows(current_user=admin))["windows"] == []


@pytest.mark.asyncio
async def test_update_missing_returns_404(patched_sm):
    with pytest.raises(HTTPException) as exc:
        await update_maintenance_window(
            str(uuid.uuid4()), _daily(), current_user=_admin()
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_emergency_override_is_created_and_audited(patched_sm):
    admin = _admin()
    host_id = str(uuid.uuid4())
    out = await create_override(
        OverrideIn(host_id=host_id, reason="ship the hotfix", duration_minutes=30),
        current_user=admin,
    )
    assert out["host_id"] == host_id
    assert out["reason"] == "ship the hotfix"
    assert out["expires_at"] is not None

    # The override must leave an audit trail.
    session = sessionmaker(bind=patched_sm)()
    try:
        audit = (
            session.query(AuditLog)
            .filter(AuditLog.entity_type == "maintenance_window")
            .all()
        )
        assert len(audit) == 1
        assert audit[0].entity_id == host_id
    finally:
        session.close()


@pytest.mark.asyncio
async def test_override_requires_reason(patched_sm):
    with pytest.raises(HTTPException) as exc:
        await create_override(
            OverrideIn(host_id=str(uuid.uuid4()), reason="  ", duration_minutes=30),
            current_user=_admin(),
        )
    assert exc.value.status_code == 400
