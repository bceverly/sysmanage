"""
Tests for the Phase 12.1.F dispatched-command tracking service.

Covers:
  * ``dispatch_command`` writes a row, refuses non-enrolled sites,
    serialises target_host_ids correctly.
  * FSM: every legal transition allowed, every illegal one raises.
  * Same-state replays are idempotent (offline reconnect safety).
  * Listing filters: by site, by status, ``open_only``.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import json
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.services import federation_dispatch_service as dsvc
from backend.services import federation_site_service as ssvc
from tests.federation_crypto import quick_enroll

FEDERATION_TABLE_NAMES = [
    "federation_sites",
    "federation_host_directory",
    "federation_host_rollup",
    "federation_compliance_rollup",
    "federation_vulnerability_rollup",
    "federation_policies",
    "federation_policy_assignments",
    "federation_dispatched_commands",
    "federation_audit_log",
    "federation_coordinator",
    "federation_sync_queue",
    "federation_received_policies",
    "federation_received_commands",
]


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in FEDERATION_TABLE_NAMES]
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


@pytest.fixture
def enrolled_site(session):
    site = quick_enroll(session, name="A", url="https://a.x")
    session.commit()
    return site


# ---------------------------------------------------------------------
# dispatch_command
# ---------------------------------------------------------------------


class TestDispatchCommand:
    def test_writes_row_with_queued_status(self, session, enrolled_site):
        cmd = dsvc.dispatch_command(
            session,
            command_type="reboot",
            target_site_id=enrolled_site.id,
            parameters={"delay_seconds": 30},
            dispatched_by="admin@x",
        )
        session.commit()
        assert cmd.id is not None
        assert cmd.status == dsvc.STATUS_QUEUED_AT_SITE
        assert cmd.target_site_id == enrolled_site.id
        assert json.loads(cmd.parameters_json) == {"delay_seconds": 30}

    def test_blank_command_type_raises(self, session, enrolled_site):
        with pytest.raises(ValueError):
            dsvc.dispatch_command(
                session,
                command_type="  ",
                target_site_id=enrolled_site.id,
            )

    def test_target_host_ids_serialised(self, session, enrolled_site):
        host_ids = [uuid.uuid4(), uuid.uuid4()]
        cmd = dsvc.dispatch_command(
            session,
            command_type="apply_updates",
            target_site_id=enrolled_site.id,
            target_host_ids=host_ids,
        )
        session.commit()
        loaded = json.loads(cmd.target_host_ids_json)
        assert len(loaded) == 2
        assert all(uuid.UUID(h) in host_ids for h in loaded)

    def test_no_target_hosts_means_all(self, session, enrolled_site):
        cmd = dsvc.dispatch_command(
            session,
            command_type="apply_updates",
            target_site_id=enrolled_site.id,
        )
        session.commit()
        assert cmd.target_host_ids_json is None

    def test_pending_site_rejected(self, session):
        site, _ = ssvc.create_site(session, name="X", url="https://x.x")
        session.commit()
        with pytest.raises(ValueError):
            dsvc.dispatch_command(
                session,
                command_type="reboot",
                target_site_id=site.id,
            )

    def test_suspended_site_rejected(self, session, enrolled_site):
        ssvc.suspend_site(session, enrolled_site.id)
        session.commit()
        with pytest.raises(ValueError):
            dsvc.dispatch_command(
                session,
                command_type="reboot",
                target_site_id=enrolled_site.id,
            )

    def test_unknown_site_raises(self, session):
        with pytest.raises(LookupError):
            dsvc.dispatch_command(
                session,
                command_type="reboot",
                target_site_id=uuid.uuid4(),
            )


# ---------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------


class TestListing:
    def test_lists_in_dispatched_at_desc_order(self, session, enrolled_site):
        a = dsvc.dispatch_command(
            session, command_type="cmd-a", target_site_id=enrolled_site.id
        )
        session.commit()
        b = dsvc.dispatch_command(
            session, command_type="cmd-b", target_site_id=enrolled_site.id
        )
        session.commit()
        rows = dsvc.list_dispatched_commands(session)
        # newest first
        assert rows[0].id == b.id
        assert rows[1].id == a.id

    def test_filter_by_site(self, session, enrolled_site):
        other = quick_enroll(session, name="Other", url="https://o.x")
        session.commit()
        dsvc.dispatch_command(
            session, command_type="x", target_site_id=enrolled_site.id
        )
        dsvc.dispatch_command(session, command_type="y", target_site_id=other.id)
        session.commit()
        rows = dsvc.list_dispatched_commands(session, site_id=enrolled_site.id)
        assert len(rows) == 1
        assert rows[0].command_type == "x"

    def test_open_only_excludes_terminal(self, session, enrolled_site):
        a = dsvc.dispatch_command(
            session, command_type="a", target_site_id=enrolled_site.id
        )
        b = dsvc.dispatch_command(
            session, command_type="b", target_site_id=enrolled_site.id
        )
        # Drive ``a`` through to completion
        dsvc.update_command_status(session, a.id, new_status=dsvc.STATUS_IN_PROGRESS)
        dsvc.update_command_status(session, a.id, new_status=dsvc.STATUS_COMPLETED)
        session.commit()
        rows = dsvc.list_dispatched_commands(session, open_only=True)
        assert [r.id for r in rows] == [b.id]


# ---------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------


class TestFsm:
    def _new_cmd(self, session, enrolled_site):
        cmd = dsvc.dispatch_command(
            session, command_type="x", target_site_id=enrolled_site.id
        )
        session.commit()
        return cmd

    def test_queued_to_in_progress(self, session, enrolled_site):
        cmd = self._new_cmd(session, enrolled_site)
        dsvc.update_command_status(session, cmd.id, new_status=dsvc.STATUS_IN_PROGRESS)
        session.commit()
        assert cmd.status == dsvc.STATUS_IN_PROGRESS
        # Non-terminal — completed_at stays NULL.
        assert cmd.completed_at is None

    def test_in_progress_to_completed(self, session, enrolled_site):
        cmd = self._new_cmd(session, enrolled_site)
        dsvc.update_command_status(session, cmd.id, new_status=dsvc.STATUS_IN_PROGRESS)
        dsvc.update_command_status(
            session,
            cmd.id,
            new_status=dsvc.STATUS_COMPLETED,
            result_summary="all 3 hosts ok",
        )
        session.commit()
        assert cmd.status == dsvc.STATUS_COMPLETED
        assert cmd.result_summary == "all 3 hosts ok"
        assert cmd.completed_at is not None

    def test_in_progress_to_partial(self, session, enrolled_site):
        cmd = self._new_cmd(session, enrolled_site)
        dsvc.update_command_status(session, cmd.id, new_status=dsvc.STATUS_IN_PROGRESS)
        dsvc.update_command_status(
            session,
            cmd.id,
            new_status=dsvc.STATUS_PARTIAL,
            result_summary="2 ok, 1 failed",
        )
        session.commit()
        assert cmd.status == dsvc.STATUS_PARTIAL
        assert cmd.completed_at is not None

    def test_queued_directly_to_failed(self, session, enrolled_site):
        """Site refused the command outright before starting."""
        cmd = self._new_cmd(session, enrolled_site)
        dsvc.update_command_status(
            session,
            cmd.id,
            new_status=dsvc.STATUS_FAILED,
            result_summary="site refused: unsupported command_type",
        )
        session.commit()
        assert cmd.status == dsvc.STATUS_FAILED
        assert cmd.completed_at is not None

    def test_terminal_cannot_be_resurrected(self, session, enrolled_site):
        cmd = self._new_cmd(session, enrolled_site)
        dsvc.update_command_status(session, cmd.id, new_status=dsvc.STATUS_IN_PROGRESS)
        dsvc.update_command_status(session, cmd.id, new_status=dsvc.STATUS_COMPLETED)
        session.commit()
        with pytest.raises(dsvc.InvalidDispatchStateError):
            dsvc.update_command_status(
                session, cmd.id, new_status=dsvc.STATUS_IN_PROGRESS
            )

    def test_queued_to_completed_disallowed(self, session, enrolled_site):
        """Sites must go through in_progress first — skipping it
        would imply the command finished before it started."""
        cmd = self._new_cmd(session, enrolled_site)
        with pytest.raises(dsvc.InvalidDispatchStateError):
            dsvc.update_command_status(
                session, cmd.id, new_status=dsvc.STATUS_COMPLETED
            )

    def test_same_state_is_idempotent(self, session, enrolled_site):
        cmd = self._new_cmd(session, enrolled_site)
        dsvc.update_command_status(session, cmd.id, new_status=dsvc.STATUS_IN_PROGRESS)
        session.commit()
        # Re-applying in_progress -> no error, no double-stamp.
        dsvc.update_command_status(session, cmd.id, new_status=dsvc.STATUS_IN_PROGRESS)
        session.commit()
        assert cmd.status == dsvc.STATUS_IN_PROGRESS

    def test_unknown_command_raises(self, session):
        with pytest.raises(dsvc.DispatchedCommandNotFoundError):
            dsvc.update_command_status(
                session, uuid.uuid4(), new_status=dsvc.STATUS_IN_PROGRESS
            )


# ---------------------------------------------------------------------------
# Phase 12.10 hardening: push-attempt tracking + backoff filter +
# dead-letter on the dispatched-command surface.
# ---------------------------------------------------------------------------


class TestPushAttemptsAndBackoff:
    def test_mark_push_failed_bumps_counter(self, session, enrolled_site):
        cmd = dsvc.dispatch_command(
            session,
            command_type="reboot",
            target_site_id=enrolled_site.id,
            parameters={},
            target_host_ids=[],
        )
        session.commit()
        dsvc.mark_push_failed(session, cmd.id, error="HTTP 502")
        session.commit()
        assert cmd.push_attempts == 1
        assert cmd.last_push_error == "HTTP 502"
        assert cmd.last_push_attempt_at is not None
        # FSM unchanged on a single failure.
        assert cmd.status == dsvc.STATUS_QUEUED_AT_SITE

    def test_mark_push_failed_dead_letters_after_max(self, session, enrolled_site):
        from backend.services import federation_retry_policy as rp

        cmd = dsvc.dispatch_command(
            session,
            command_type="reboot",
            target_site_id=enrolled_site.id,
            parameters={},
            target_host_ids=[],
        )
        session.commit()
        for _ in range(rp.MAX_ATTEMPTS):
            dsvc.mark_push_failed(session, cmd.id, error="net down")
        session.commit()
        assert cmd.push_attempts == rp.MAX_ATTEMPTS
        # Once dead-lettered, FSM advances to terminal failed.
        assert cmd.status == dsvc.STATUS_FAILED
        assert cmd.completed_at is not None
        assert "Push failed after" in (cmd.result_summary or "")

    def test_mark_push_failed_requires_error_string(self, session, enrolled_site):
        cmd = dsvc.dispatch_command(
            session,
            command_type="reboot",
            target_site_id=enrolled_site.id,
            parameters={},
            target_host_ids=[],
        )
        session.commit()
        with pytest.raises(ValueError):
            dsvc.mark_push_failed(session, cmd.id, error="")

    def test_ready_only_excludes_dead_lettered(self, session, enrolled_site):
        from backend.services import federation_retry_policy as rp

        cmd = dsvc.dispatch_command(
            session,
            command_type="reboot",
            target_site_id=enrolled_site.id,
            parameters={},
            target_host_ids=[],
        )
        session.commit()
        for _ in range(rp.MAX_ATTEMPTS):
            dsvc.mark_push_failed(session, cmd.id, error="boom")
        session.commit()
        rows = dsvc.list_dispatched_commands(
            session, status=dsvc.STATUS_QUEUED_AT_SITE, ready_only=True
        )
        assert rows == []

    def test_ready_only_filters_recently_failed(self, session, enrolled_site):
        from datetime import datetime as _dt

        cmd = dsvc.dispatch_command(
            session,
            command_type="reboot",
            target_site_id=enrolled_site.id,
            parameters={},
            target_host_ids=[],
        )
        session.commit()
        dsvc.mark_push_failed(session, cmd.id, error="transient")
        session.commit()
        not_yet = dsvc.list_dispatched_commands(
            session,
            status=dsvc.STATUS_QUEUED_AT_SITE,
            ready_only=True,
            now=_dt.utcnow().replace(tzinfo=None),
        )
        assert not_yet == []

    def test_ready_only_releases_after_window(self, session, enrolled_site):
        from datetime import datetime as _dt, timedelta

        cmd = dsvc.dispatch_command(
            session,
            command_type="reboot",
            target_site_id=enrolled_site.id,
            parameters={},
            target_host_ids=[],
        )
        session.commit()
        dsvc.mark_push_failed(session, cmd.id, error="transient")
        session.commit()
        future = _dt.utcnow().replace(tzinfo=None) + timedelta(hours=2)
        ready = dsvc.list_dispatched_commands(
            session,
            status=dsvc.STATUS_QUEUED_AT_SITE,
            ready_only=True,
            now=future,
        )
        assert len(ready) == 1
        assert ready[0].id == cmd.id
