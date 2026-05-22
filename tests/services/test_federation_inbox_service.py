"""
Tests for the Phase 12.2 site-side inbox service.

Covers:
  * Policy inbox: upsert-on-receive with version-based dedup,
    apply / apply-failed transitions, list-unapplied filtering.
  * Command inbox: receive (with FSM), list-queued ordering,
    update-status FSM transitions including terminal absorption
    and idempotent same-state replays.
  * Re-push of a completed command from the coordinator is a no-op
    (doesn't reset to queued).
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import json
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.services import federation_inbox_service as ibx

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


# =====================================================================
# Policy inbox
# =====================================================================


class TestReceivePolicy:
    def test_creates_unapplied_row(self, session):
        pid = uuid.uuid4()
        row = ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="update_profile",
            name="weekly",
            definition={"day": "tue"},
            version=1,
        )
        session.commit()
        assert row.policy_id == pid
        assert row.applied is False
        assert row.received_at is not None
        assert json.loads(row.definition_json) == {"day": "tue"}

    def test_blank_type_raises(self, session):
        with pytest.raises(ValueError):
            ibx.receive_policy(
                session,
                policy_id=uuid.uuid4(),
                policy_type="",
                name="x",
                definition={},
                version=1,
            )

    def test_blank_name_raises(self, session):
        with pytest.raises(ValueError):
            ibx.receive_policy(
                session,
                policy_id=uuid.uuid4(),
                policy_type="x",
                name="   ",
                definition={},
                version=1,
            )

    def test_non_dict_definition_raises(self, session):
        with pytest.raises(ValueError):
            ibx.receive_policy(
                session,
                policy_id=uuid.uuid4(),
                policy_type="x",
                name="y",
                definition="not a dict",  # type: ignore[arg-type]
                version=1,
            )

    def test_zero_version_raises(self, session):
        with pytest.raises(ValueError):
            ibx.receive_policy(
                session,
                policy_id=uuid.uuid4(),
                policy_type="x",
                name="y",
                definition={},
                version=0,
            )

    def test_replay_same_version_is_noop(self, session):
        pid = uuid.uuid4()
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="orig",
            definition={"a": 1},
            version=1,
        )
        ibx.mark_policy_applied(session, pid)
        session.commit()
        # Re-push of the same version: should NOT revert applied state.
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="orig",
            definition={"a": 1},
            version=1,
        )
        session.commit()
        row = ibx.get_received_policy(session, pid)
        assert row.applied is True

    def test_newer_version_resets_applied(self, session):
        pid = uuid.uuid4()
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="orig",
            definition={"a": 1},
            version=1,
        )
        ibx.mark_policy_applied(session, pid)
        session.commit()
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="updated",
            definition={"a": 2},
            version=2,
        )
        session.commit()
        row = ibx.get_received_policy(session, pid)
        assert row.applied is False
        assert row.name == "updated"
        assert json.loads(row.definition_json) == {"a": 2}

    def test_older_version_ignored(self, session):
        """Out-of-order delivery: coordinator pushed v3 first, v2 second.
        The v2 push must NOT downgrade the local v3 state."""
        pid = uuid.uuid4()
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="v3",
            definition={"v": 3},
            version=3,
        )
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="v2",
            definition={"v": 2},
            version=2,
        )
        session.commit()
        row = ibx.get_received_policy(session, pid)
        assert row.version == 3
        assert json.loads(row.definition_json) == {"v": 3}


class TestListUnappliedPolicies:
    def test_filters_by_applied(self, session):
        pid_unapplied = uuid.uuid4()
        pid_applied = uuid.uuid4()
        ibx.receive_policy(
            session,
            policy_id=pid_unapplied,
            policy_type="x",
            name="a",
            definition={},
            version=1,
        )
        ibx.receive_policy(
            session,
            policy_id=pid_applied,
            policy_type="x",
            name="b",
            definition={},
            version=1,
        )
        ibx.mark_policy_applied(session, pid_applied)
        session.commit()
        rows = ibx.list_unapplied_policies(session)
        assert [r.policy_id for r in rows] == [pid_unapplied]

    def test_filters_by_type(self, session):
        ibx.receive_policy(
            session,
            policy_id=uuid.uuid4(),
            policy_type="firewall_role",
            name="a",
            definition={},
            version=1,
        )
        ibx.receive_policy(
            session,
            policy_id=uuid.uuid4(),
            policy_type="update_profile",
            name="b",
            definition={},
            version=1,
        )
        session.commit()
        fws = ibx.list_unapplied_policies(session, policy_type="firewall_role")
        assert len(fws) == 1
        assert fws[0].policy_type == "firewall_role"


class TestApplyTransitions:
    def test_mark_applied_clears_error(self, session):
        pid = uuid.uuid4()
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="y",
            definition={},
            version=1,
        )
        ibx.mark_policy_apply_failed(session, pid, error="boom")
        session.commit()
        ibx.mark_policy_applied(session, pid)
        session.commit()
        row = ibx.get_received_policy(session, pid)
        assert row.applied is True
        assert row.applied_at is not None
        assert row.apply_error is None

    def test_mark_applied_idempotent(self, session):
        pid = uuid.uuid4()
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="y",
            definition={},
            version=1,
        )
        ibx.mark_policy_applied(session, pid)
        session.commit()
        first_applied_at = ibx.get_received_policy(session, pid).applied_at
        # Re-call: applied_at MUST NOT advance.
        ibx.mark_policy_applied(session, pid)
        session.commit()
        assert ibx.get_received_policy(session, pid).applied_at == first_applied_at

    def test_mark_apply_failed_blank_error_raises(self, session):
        pid = uuid.uuid4()
        ibx.receive_policy(
            session,
            policy_id=pid,
            policy_type="x",
            name="y",
            definition={},
            version=1,
        )
        with pytest.raises(ValueError):
            ibx.mark_policy_apply_failed(session, pid, error="")


# =====================================================================
# Command inbox
# =====================================================================


class TestReceiveCommand:
    def test_creates_queued_row(self, session):
        cid = uuid.uuid4()
        row = ibx.receive_command(
            session,
            command_id=cid,
            command_type="reboot",
            parameters={"delay": 30},
        )
        session.commit()
        assert row.id == cid
        assert row.status == ibx.CMD_STATUS_QUEUED
        assert json.loads(row.parameters_json) == {"delay": 30}

    def test_target_host_ids_serialised(self, session):
        cid = uuid.uuid4()
        hosts = [uuid.uuid4(), uuid.uuid4()]
        ibx.receive_command(
            session,
            command_id=cid,
            command_type="apply_updates",
            target_host_ids=hosts,
        )
        session.commit()
        row = ibx.get_received_command(session, cid)
        loaded = json.loads(row.target_host_ids_json)
        assert len(loaded) == 2

    def test_no_target_hosts_means_all(self, session):
        cid = uuid.uuid4()
        ibx.receive_command(session, command_id=cid, command_type="apply_updates")
        session.commit()
        row = ibx.get_received_command(session, cid)
        assert row.target_host_ids_json is None

    def test_blank_command_type_raises(self, session):
        with pytest.raises(ValueError):
            ibx.receive_command(session, command_id=uuid.uuid4(), command_type="")

    def test_replay_of_completed_is_noop(self, session):
        cid = uuid.uuid4()
        ibx.receive_command(session, command_id=cid, command_type="reboot")
        ibx.update_command_status(
            session,
            cid,
            new_status=ibx.CMD_STATUS_IN_PROGRESS,
        )
        ibx.update_command_status(
            session,
            cid,
            new_status=ibx.CMD_STATUS_COMPLETED,
            result={"all_ok": True},
        )
        session.commit()
        # Re-push by coordinator: state must STAY completed.
        ibx.receive_command(session, command_id=cid, command_type="reboot")
        session.commit()
        row = ibx.get_received_command(session, cid)
        assert row.status == ibx.CMD_STATUS_COMPLETED

    def test_replay_while_in_flight_refreshes_params(self, session):
        cid = uuid.uuid4()
        ibx.receive_command(
            session,
            command_id=cid,
            command_type="apply_updates",
            parameters={"packages": ["a"]},
        )
        session.commit()
        # Coordinator amended the command before we got around to it.
        ibx.receive_command(
            session,
            command_id=cid,
            command_type="apply_updates",
            parameters={"packages": ["a", "b"]},
        )
        session.commit()
        row = ibx.get_received_command(session, cid)
        assert json.loads(row.parameters_json) == {"packages": ["a", "b"]}


class TestListQueuedCommands:
    def test_returns_only_queued(self, session):
        a = uuid.uuid4()
        b = uuid.uuid4()
        ibx.receive_command(session, command_id=a, command_type="x")
        ibx.receive_command(session, command_id=b, command_type="y")
        ibx.update_command_status(session, a, new_status=ibx.CMD_STATUS_IN_PROGRESS)
        session.commit()
        rows = ibx.list_queued_commands(session)
        assert [r.id for r in rows] == [b]

    def test_limit_zero_raises(self, session):
        with pytest.raises(ValueError):
            ibx.list_queued_commands(session, limit=0)


class TestCommandFsm:
    def _new(self, session):
        cid = uuid.uuid4()
        ibx.receive_command(session, command_id=cid, command_type="reboot")
        session.commit()
        return cid

    def test_queued_to_in_progress(self, session):
        cid = self._new(session)
        ibx.update_command_status(session, cid, new_status=ibx.CMD_STATUS_IN_PROGRESS)
        session.commit()
        assert (
            ibx.get_received_command(session, cid).status == ibx.CMD_STATUS_IN_PROGRESS
        )

    def test_in_progress_to_completed_with_result(self, session):
        cid = self._new(session)
        ibx.update_command_status(session, cid, new_status=ibx.CMD_STATUS_IN_PROGRESS)
        ibx.update_command_status(
            session,
            cid,
            new_status=ibx.CMD_STATUS_COMPLETED,
            result={"all_ok": True},
        )
        session.commit()
        row = ibx.get_received_command(session, cid)
        assert row.status == ibx.CMD_STATUS_COMPLETED
        assert row.completed_at is not None
        assert json.loads(row.result_json) == {"all_ok": True}

    def test_queued_to_failed_direct(self, session):
        cid = self._new(session)
        ibx.update_command_status(
            session,
            cid,
            new_status=ibx.CMD_STATUS_FAILED,
            result={"error": "agent missing"},
        )
        session.commit()
        row = ibx.get_received_command(session, cid)
        assert row.status == ibx.CMD_STATUS_FAILED
        assert row.completed_at is not None

    def test_terminal_cannot_be_resurrected(self, session):
        cid = self._new(session)
        ibx.update_command_status(session, cid, new_status=ibx.CMD_STATUS_IN_PROGRESS)
        ibx.update_command_status(session, cid, new_status=ibx.CMD_STATUS_COMPLETED)
        session.commit()
        with pytest.raises(ibx.InvalidCommandStateError):
            ibx.update_command_status(
                session, cid, new_status=ibx.CMD_STATUS_IN_PROGRESS
            )

    def test_queued_directly_to_completed_disallowed(self, session):
        cid = self._new(session)
        with pytest.raises(ibx.InvalidCommandStateError):
            ibx.update_command_status(session, cid, new_status=ibx.CMD_STATUS_COMPLETED)

    def test_same_state_is_idempotent(self, session):
        cid = self._new(session)
        ibx.update_command_status(session, cid, new_status=ibx.CMD_STATUS_IN_PROGRESS)
        # Re-applying in_progress is fine — worker restart safety.
        ibx.update_command_status(session, cid, new_status=ibx.CMD_STATUS_IN_PROGRESS)
        session.commit()
        assert (
            ibx.get_received_command(session, cid).status == ibx.CMD_STATUS_IN_PROGRESS
        )

    def test_unknown_command_raises(self, session):
        with pytest.raises(ibx.ReceivedCommandNotFoundError):
            ibx.update_command_status(
                session,
                uuid.uuid4(),
                new_status=ibx.CMD_STATUS_IN_PROGRESS,
            )
