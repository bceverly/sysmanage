# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for backend/services/maintenance_window_service.py (Phase 14.2).

Covers the gating policy (opt-in, allow-inside, blackout-wins, override-beats-all)
and the timezone-aware recurrence math.
"""

import uuid
from datetime import datetime, timedelta

from backend.persistence.models import (
    Host,
    MaintenanceOverride,
    MaintenanceWindow,
    MaintenanceWindowScope,
)
from backend.persistence.models.operations import HostTag, Tag
from backend.services import maintenance_window_service as mw

# A fixed reference "now" (naive UTC): Saturday 2026-07-11 12:00.
NOW = datetime(2026, 7, 11, 12, 0)


def _mk_window(db, scopes, **kw):
    """Create a window + its scope rows.  scopes = list of (type, host_id, tag_id)."""
    window = MaintenanceWindow(
        name=kw.get("name", "w"),
        kind=kw.get("kind", "allow"),
        recurrence=kw.get("recurrence", "daily"),
        timezone=kw.get("timezone", "UTC"),
        start_time=kw.get("start_time", "00:00"),
        duration_minutes=kw.get("duration_minutes", 1440),
        days_of_week=kw.get("days_of_week"),
        starts_at=kw.get("starts_at"),
        ends_at=kw.get("ends_at"),
        enabled=kw.get("enabled", True),
    )
    db.add(window)
    db.flush()
    for scope_type, host_id, tag_id in scopes:
        db.add(
            MaintenanceWindowScope(
                window_id=window.id,
                scope_type=scope_type,
                host_id=host_id,
                tag_id=tag_id,
            )
        )
    db.commit()
    return window


class TestGatingPolicy:
    """is_dispatch_allowed decision matrix."""

    def test_no_windows_is_unrestricted(self, db_session):
        assert mw.is_dispatch_allowed(db_session, uuid.uuid4(), NOW) is True

    def test_allow_window_open_permits(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            start_time="10:00",
            duration_minutes=240,  # 10:00–14:00 contains 12:00
        )
        assert mw.is_dispatch_allowed(db_session, host, NOW) is True

    def test_allow_window_closed_blocks(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            start_time="02:00",
            duration_minutes=60,  # 02:00–03:00 does NOT contain 12:00
        )
        assert mw.is_dispatch_allowed(db_session, host, NOW) is False

    def test_window_scoped_to_other_host_does_not_restrict(self, db_session):
        other = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", other, None)],
            start_time="02:00",
            duration_minutes=60,
        )
        # A different host has no window applying → unrestricted.
        assert mw.is_dispatch_allowed(db_session, uuid.uuid4(), NOW) is True

    def test_blackout_beats_open_allow(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            name="allow",
            start_time="10:00",
            duration_minutes=240,
        )
        _mk_window(
            db_session,
            [("host", host, None)],
            name="blackout",
            kind="blackout",
            start_time="11:30",
            duration_minutes=60,  # 11:30–12:30 contains 12:00
        )
        assert mw.is_dispatch_allowed(db_session, host, NOW) is False

    def test_blackout_only_when_inactive_is_unrestricted(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            kind="blackout",
            start_time="02:00",
            duration_minutes=60,  # inactive at 12:00
        )
        # Only a (currently inactive) blackout applies → unrestricted.
        assert mw.is_dispatch_allowed(db_session, host, NOW) is True

    def test_disabled_window_ignored(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            start_time="02:00",
            duration_minutes=60,
            enabled=False,
        )
        assert mw.is_dispatch_allowed(db_session, host, NOW) is True

    def test_active_override_beats_closed_window(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            start_time="02:00",
            duration_minutes=60,  # closed at 12:00
        )
        db_session.add(
            MaintenanceOverride(
                host_id=host,
                reason="emergency patch",
                expires_at=NOW + timedelta(hours=1),
                created_at=NOW,
            )
        )
        db_session.commit()
        assert mw.is_dispatch_allowed(db_session, host, NOW) is True

    def test_expired_override_does_not_help(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            start_time="02:00",
            duration_minutes=60,
        )
        db_session.add(
            MaintenanceOverride(
                host_id=host,
                reason="stale",
                expires_at=NOW - timedelta(minutes=5),
                created_at=NOW - timedelta(hours=2),
            )
        )
        db_session.commit()
        assert mw.is_dispatch_allowed(db_session, host, NOW) is False


class TestTagScope:
    """A tag-scoped window applies to every host carrying the tag."""

    def _host_with_tag(self, db):
        host = Host(fqdn="h1.example", active=True, approval_status="approved")
        db.add(host)
        tag = Tag(name="prod", created_at=NOW, updated_at=NOW)
        db.add(tag)
        db.flush()
        db.add(HostTag(host_id=host.id, tag_id=tag.id, created_at=NOW))
        db.commit()
        return host, tag

    def test_tag_window_applies(self, db_session):
        host, tag = self._host_with_tag(db_session)
        _mk_window(
            db_session,
            [("tag", None, tag.id)],
            start_time="02:00",
            duration_minutes=60,  # closed at 12:00
        )
        # The host carries the tag, so the (closed) window restricts it.
        assert mw.is_dispatch_allowed(db_session, host.id, NOW) is False

    def test_all_scope_applies_to_any_host(self, db_session):
        _mk_window(
            db_session,
            [("all", None, None)],
            start_time="02:00",
            duration_minutes=60,
        )
        assert mw.is_dispatch_allowed(db_session, uuid.uuid4(), NOW) is False


class TestNextWindow:
    """next_window_for_host state + next-start reporting."""

    def test_unrestricted_state(self, db_session):
        out = mw.next_window_for_host(db_session, uuid.uuid4(), NOW)
        assert out["state"] == "unrestricted"
        assert out["next_window"] is None

    def test_in_window_state_reports_current(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            start_time="10:00",
            duration_minutes=240,
        )
        out = mw.next_window_for_host(db_session, host, NOW)
        assert out["state"] == "in_window"
        assert out["next_window"]["starts_at"] is not None

    def test_blocked_state_reports_next_start(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            start_time="20:00",
            duration_minutes=60,  # closed at 12:00; opens 20:00 today
        )
        out = mw.next_window_for_host(db_session, host, NOW)
        assert out["state"] == "blocked"
        assert out["next_window"]["starts_at"].startswith("2026-07-11T20:00")

    def test_override_state(self, db_session):
        host = uuid.uuid4()
        db_session.add(
            MaintenanceOverride(
                host_id=host,
                reason="x",
                expires_at=NOW + timedelta(hours=1),
                created_at=NOW,
            )
        )
        db_session.commit()
        out = mw.next_window_for_host(db_session, host, NOW)
        assert out["state"] == "override"
        assert out["override"]["reason"] == "x"


class TestOnceRecurrence:
    """One-off windows use absolute UTC bounds."""

    def test_once_contains(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            recurrence="once",
            start_time=None,
            duration_minutes=None,
            starts_at=NOW - timedelta(hours=1),
            ends_at=NOW + timedelta(hours=1),
        )
        assert mw.is_dispatch_allowed(db_session, host, NOW) is True

    def test_once_past_blocks(self, db_session):
        host = uuid.uuid4()
        _mk_window(
            db_session,
            [("host", host, None)],
            recurrence="once",
            start_time=None,
            duration_minutes=None,
            starts_at=NOW - timedelta(hours=3),
            ends_at=NOW - timedelta(hours=1),
        )
        assert mw.is_dispatch_allowed(db_session, host, NOW) is False
