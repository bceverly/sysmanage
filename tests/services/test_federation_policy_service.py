"""
Tests for the Phase 12.1.F federation policy service.

Covers:
  * Policy CRUD: create, get, list (with type filter + active-only),
    update (with version bumping + uniqueness), deactivate (idempotent).
  * Assignment: idempotent assign, unassign, list-by-policy + list-by-site,
    push status transitions.
  * Stale-version detection: ``list_pending_push_targets`` includes
    rows whose ``pushed_version`` lags the current ``policy.version``.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import json

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import FederationAuditLog
from backend.services import federation_policy_service as psvc
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
# Policy CRUD
# ---------------------------------------------------------------------


class TestCreatePolicy:
    def test_persists_with_version_one(self, session):
        policy = psvc.create_policy(
            session,
            policy_type="update_profile",
            name="weekly-tuesday",
            definition={"day_of_week": "tue", "hour": 22},
            created_by="admin@x",
        )
        session.commit()
        assert policy.id is not None
        assert policy.version == 1
        assert policy.is_active is True
        assert json.loads(policy.definition_json) == {
            "day_of_week": "tue",
            "hour": 22,
        }

    def test_duplicate_type_name_raises(self, session):
        psvc.create_policy(
            session,
            policy_type="firewall_role",
            name="web-tier",
            definition={"ports": [80, 443]},
        )
        session.commit()
        with pytest.raises(psvc.PolicyNameConflictError):
            psvc.create_policy(
                session,
                policy_type="firewall_role",
                name="web-tier",
                definition={"ports": [443]},
            )

    def test_same_name_different_type_ok(self, session):
        psvc.create_policy(
            session,
            policy_type="firewall_role",
            name="standard",
            definition={},
        )
        psvc.create_policy(
            session,
            policy_type="update_profile",
            name="standard",
            definition={},
        )
        session.commit()
        assert len(psvc.list_policies(session)) == 2

    def test_blank_type_raises(self, session):
        with pytest.raises(ValueError):
            psvc.create_policy(session, policy_type="  ", name="x", definition={})

    def test_blank_name_raises(self, session):
        with pytest.raises(ValueError):
            psvc.create_policy(session, policy_type="x", name="  ", definition={})

    def test_non_dict_definition_raises(self, session):
        with pytest.raises(ValueError):
            psvc.create_policy(
                session,
                policy_type="x",
                name="y",
                definition="not a dict",  # type: ignore[arg-type]
            )

    def test_audits_creation(self, session):
        psvc.create_policy(
            session,
            policy_type="x",
            name="y",
            definition={},
            created_by="admin@x",
        )
        session.commit()
        entries = (
            session.query(FederationAuditLog)
            .filter_by(operation=psvc.AUDIT_OP_POLICY_CREATED)
            .all()
        )
        assert len(entries) == 1


class TestListPolicies:
    def test_filters_by_type(self, session):
        psvc.create_policy(session, policy_type="a", name="p1", definition={})
        psvc.create_policy(session, policy_type="a", name="p2", definition={})
        psvc.create_policy(session, policy_type="b", name="p3", definition={})
        session.commit()
        as_type_a = psvc.list_policies(session, policy_type="a")
        assert len(as_type_a) == 2

    def test_active_only_excludes_deactivated(self, session):
        p1 = psvc.create_policy(session, policy_type="x", name="active", definition={})
        p2 = psvc.create_policy(session, policy_type="x", name="dead", definition={})
        psvc.deactivate_policy(session, p2.id)
        session.commit()
        assert {p.id for p in psvc.list_policies(session)} == {p1.id}
        assert len(psvc.list_policies(session, active_only=False)) == 2


class TestUpdatePolicy:
    def test_renames_and_bumps_version(self, session):
        p = psvc.create_policy(
            session, policy_type="x", name="old-name", definition={"a": 1}
        )
        session.commit()
        psvc.update_policy(session, p.id, name="new-name")
        session.commit()
        assert p.name == "new-name"
        assert p.version == 2

    def test_definition_change_bumps_version(self, session):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={"a": 1})
        session.commit()
        psvc.update_policy(session, p.id, definition={"a": 2})
        session.commit()
        assert p.version == 2
        assert json.loads(p.definition_json) == {"a": 2}

    def test_no_op_update_does_not_bump_version(self, session):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={"a": 1})
        session.commit()
        psvc.update_policy(session, p.id, definition={"a": 1})  # same body
        session.commit()
        assert p.version == 1

    def test_rename_collision_raises(self, session):
        psvc.create_policy(session, policy_type="x", name="a", definition={})
        p2 = psvc.create_policy(session, policy_type="x", name="b", definition={})
        session.commit()
        with pytest.raises(psvc.PolicyNameConflictError):
            psvc.update_policy(session, p2.id, name="a")

    def test_rename_same_name_different_type_ok(self, session):
        psvc.create_policy(session, policy_type="x", name="a", definition={})
        p_y = psvc.create_policy(session, policy_type="y", name="b", definition={})
        session.commit()
        # Renaming p_y to "a" is fine because uniqueness is per-type.
        psvc.update_policy(session, p_y.id, name="a")
        session.commit()
        assert p_y.name == "a"

    def test_unknown_field_raises(self, session):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        with pytest.raises(ValueError):
            psvc.update_policy(session, p.id, policy_type="other")

    def test_cannot_update_deactivated_policy(self, session):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.deactivate_policy(session, p.id)
        session.commit()
        with pytest.raises(ValueError):
            psvc.update_policy(session, p.id, name="new")


class TestDeactivate:
    def test_flips_is_active(self, session):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.deactivate_policy(session, p.id)
        session.commit()
        assert p.is_active is False

    def test_idempotent_on_already_inactive(self, session):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.deactivate_policy(session, p.id)
        session.commit()
        before = session.query(FederationAuditLog).count()
        psvc.deactivate_policy(session, p.id)
        session.commit()
        assert session.query(FederationAuditLog).count() == before


# ---------------------------------------------------------------------
# Policy assignment
# ---------------------------------------------------------------------


class TestAssignment:
    def test_assigns_to_multiple_sites(self, session, enrolled_site):
        s2 = quick_enroll(session, name="B", url="https://b.x")
        session.commit()
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id, s2.id])
        session.commit()
        rows = psvc.list_assignments_for_policy(session, p.id)
        assert len(rows) == 2
        assert all(r.push_status == psvc.PUSH_STATUS_PENDING for r in rows)

    def test_reassignment_resets_to_pending(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        session.commit()
        psvc.mark_policy_pushed(session, p.id, enrolled_site.id, pushed_version=1)
        session.commit()

        # Re-assign should reset push status to pending.
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        session.commit()
        rows = psvc.list_assignments_for_policy(session, p.id)
        assert rows[0].push_status == psvc.PUSH_STATUS_PENDING
        assert rows[0].last_push_error is None

    def test_assignment_inactive_policy_raises(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.deactivate_policy(session, p.id)
        session.commit()
        with pytest.raises(ValueError):
            psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])

    def test_unassign_returns_true_when_removed(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        session.commit()
        assert psvc.unassign_policy_from_site(session, p.id, enrolled_site.id) is True
        session.commit()
        assert psvc.list_assignments_for_policy(session, p.id) == []

    def test_unassign_returns_false_when_absent(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        assert psvc.unassign_policy_from_site(session, p.id, enrolled_site.id) is False

    def test_list_assignments_for_site(self, session, enrolled_site):
        p1 = psvc.create_policy(session, policy_type="x", name="a", definition={})
        p2 = psvc.create_policy(session, policy_type="y", name="b", definition={})
        psvc.assign_policy_to_sites(session, p1.id, [enrolled_site.id])
        psvc.assign_policy_to_sites(session, p2.id, [enrolled_site.id])
        session.commit()
        rows = psvc.list_assignments_for_site(session, enrolled_site.id)
        assert len(rows) == 2


# ---------------------------------------------------------------------
# Push status tracking
# ---------------------------------------------------------------------


class TestPushStatus:
    def test_mark_pushed_records_version(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        session.commit()
        psvc.mark_policy_pushed(session, p.id, enrolled_site.id, pushed_version=1)
        session.commit()
        rows = psvc.list_assignments_for_policy(session, p.id)
        assert rows[0].push_status == psvc.PUSH_STATUS_PUSHED
        assert rows[0].pushed_version == 1

    def test_mark_push_failed_records_error(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        session.commit()
        psvc.mark_policy_push_failed(
            session, p.id, enrolled_site.id, error="conn refused"
        )
        session.commit()
        rows = psvc.list_assignments_for_policy(session, p.id)
        assert rows[0].push_status == psvc.PUSH_STATUS_ERROR
        assert rows[0].last_push_error == "conn refused"

    def test_failed_then_pushed_clears_error(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        psvc.mark_policy_push_failed(session, p.id, enrolled_site.id, error="boom")
        session.commit()
        psvc.mark_policy_pushed(session, p.id, enrolled_site.id, pushed_version=1)
        session.commit()
        rows = psvc.list_assignments_for_policy(session, p.id)
        assert rows[0].last_push_error is None

    def test_mark_pushed_with_unknown_assignment_raises(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        with pytest.raises(psvc.PolicyAssignmentNotFoundError):
            psvc.mark_policy_pushed(session, p.id, enrolled_site.id, pushed_version=1)


class TestPendingPushTargets:
    def test_includes_never_pushed(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        session.commit()
        targets = psvc.list_pending_push_targets(session, p.id)
        assert len(targets) == 1

    def test_excludes_pushed_at_current_version(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        psvc.mark_policy_pushed(session, p.id, enrolled_site.id, pushed_version=1)
        session.commit()
        targets = psvc.list_pending_push_targets(session, p.id)
        assert targets == []

    def test_includes_stale_after_edit(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={"a": 1})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        psvc.mark_policy_pushed(session, p.id, enrolled_site.id, pushed_version=1)
        # Edit -> bumps version to 2; pushed_version still 1.
        psvc.update_policy(session, p.id, definition={"a": 2})
        session.commit()
        targets = psvc.list_pending_push_targets(session, p.id)
        assert len(targets) == 1
        assert targets[0].pushed_version == 1


# ---------------------------------------------------------------------------
# Phase 12.10 hardening: backoff + dead-letter integration with policy
# assignments.
# ---------------------------------------------------------------------------


class TestPushBackoffAndDeadLetter:
    def test_failure_bumps_push_attempts(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        session.commit()
        assignment = psvc.mark_policy_push_failed(
            session, p.id, enrolled_site.id, error="HTTP 500"
        )
        session.commit()
        assert assignment.push_attempts == 1
        assert assignment.push_status == psvc.PUSH_STATUS_ERROR

    def test_dead_letter_after_max_attempts(self, session, enrolled_site):
        # Simulate MAX_ATTEMPTS failures.  The first MAX-1 leave the
        # row in ``error``; the MAX-th flips to ``dead``.
        from backend.services import federation_retry_policy as rp

        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        session.commit()
        for _ in range(rp.MAX_ATTEMPTS - 1):
            psvc.mark_policy_push_failed(
                session, p.id, enrolled_site.id, error="HTTP 500"
            )
        session.commit()
        a = psvc.mark_policy_push_failed(
            session, p.id, enrolled_site.id, error="HTTP 500"
        )
        session.commit()
        assert a.push_attempts == rp.MAX_ATTEMPTS
        assert a.push_status == psvc.PUSH_STATUS_DEAD

    def test_dead_letter_excluded_from_pending_pushes(self, session, enrolled_site):
        # Dead-lettered assignments must never appear in the push
        # worker's view — that's the whole point.
        from backend.services import federation_retry_policy as rp

        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        for _ in range(rp.MAX_ATTEMPTS):
            psvc.mark_policy_push_failed(session, p.id, enrolled_site.id, error="boom")
        session.commit()
        pending = psvc.list_all_pending_pushes(session)
        assert pending == []

    def test_re_assignment_resets_attempts(self, session, enrolled_site):
        # Operator re-assigning a dead-lettered policy gives it a
        # fresh window.
        from backend.services import federation_retry_policy as rp

        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        for _ in range(rp.MAX_ATTEMPTS):
            psvc.mark_policy_push_failed(session, p.id, enrolled_site.id, error="boom")
        session.commit()
        # Re-assign.
        psvc.assign_policy_to_sites(
            session, p.id, [enrolled_site.id], assigned_by="operator"
        )
        session.commit()
        # ``now`` far in the future so the new (zero) attempts +
        # never-attempted ``last_push_attempt_at`` clearly pass the
        # backoff filter.
        from datetime import datetime as _dt, timedelta

        future = _dt.utcnow().replace(tzinfo=None) + timedelta(hours=2)
        pending = psvc.list_all_pending_pushes(session, now=future)
        assert len(pending) == 1
        _, a = pending[0]
        assert a.push_attempts == 0
        assert a.push_status == psvc.PUSH_STATUS_PENDING

    def test_backoff_filters_recently_failed(self, session, enrolled_site):
        # Just-failed assignments are still in their backoff window
        # and shouldn't appear in the worker's view immediately.
        from datetime import datetime as _dt

        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        psvc.mark_policy_push_failed(session, p.id, enrolled_site.id, error="transient")
        session.commit()
        not_yet = psvc.list_all_pending_pushes(
            session, now=_dt.utcnow().replace(tzinfo=None)
        )
        assert not_yet == []

    def test_backoff_releases_after_window(self, session, enrolled_site):
        # ``now`` far in the future → past the backoff cap, ready.
        from datetime import datetime as _dt, timedelta

        p = psvc.create_policy(session, policy_type="x", name="y", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        psvc.mark_policy_push_failed(session, p.id, enrolled_site.id, error="transient")
        session.commit()
        future = _dt.utcnow().replace(tzinfo=None) + timedelta(hours=2)
        ready = psvc.list_all_pending_pushes(session, now=future)
        assert len(ready) == 1


class TestRequeueSitePolicies:
    def test_resets_assignments_to_pending(self, session, enrolled_site):
        p1 = psvc.create_policy(session, policy_type="x", name="p1", definition={})
        p2 = psvc.create_policy(session, policy_type="x", name="p2", definition={})
        psvc.assign_policy_to_sites(session, p1.id, [enrolled_site.id])
        psvc.assign_policy_to_sites(session, p2.id, [enrolled_site.id])
        # Mark both as pushed so requeue has something to reset.
        psvc.mark_policy_pushed(session, p1.id, enrolled_site.id, pushed_version=1)
        psvc.mark_policy_pushed(session, p2.id, enrolled_site.id, pushed_version=1)
        session.commit()

        affected = psvc.requeue_site_policies(session, enrolled_site.id)
        session.commit()
        assert len(affected) == 2
        rows = psvc.list_assignments_for_site(session, enrolled_site.id)
        assert all(r.push_status == psvc.PUSH_STATUS_PENDING for r in rows)

    def test_rescues_dead_lettered_assignment(self, session, enrolled_site):
        p = psvc.create_policy(session, policy_type="x", name="p", definition={})
        psvc.assign_policy_to_sites(session, p.id, [enrolled_site.id])
        row = psvc.list_assignments_for_site(session, enrolled_site.id)[0]
        row.push_status = psvc.PUSH_STATUS_DEAD
        row.push_attempts = 99
        row.last_push_error = "gave up"
        session.commit()

        psvc.requeue_site_policies(session, enrolled_site.id)
        session.commit()
        row = psvc.list_assignments_for_site(session, enrolled_site.id)[0]
        assert row.push_status == psvc.PUSH_STATUS_PENDING
        assert row.push_attempts == 0
        assert row.last_push_error is None

    def test_empty_when_site_has_no_policies(self, session, enrolled_site):
        assert psvc.requeue_site_policies(session, enrolled_site.id) == []

    def test_unknown_site_raises_lookup(self, session):
        import uuid as _uuid

        with pytest.raises(LookupError):
            psvc.requeue_site_policies(session, _uuid.uuid4())
