# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the site-side federation actuation service (Phase 12.2).

Covers command fan-out to local agents (queued, never called directly),
per-host result aggregation, terminal-state settling, and the upstream
``command_result`` sync-queue packet.
"""

import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.persistence.models.federation import FederationSyncQueue
from backend.services import federation_actuation_service as actuation
from backend.services import federation_inbox_service as inbox_svc


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine, checkfirst=True)
    testing_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sess = testing_local()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


class FakeQueueOps:
    """Records enqueue_message calls instead of touching a real queue."""

    def __init__(self):
        self.calls = []

    def enqueue_message(  # pylint: disable=too-many-arguments
        self,
        *,
        message_type,
        message_data,
        direction,
        host_id=None,
        message_id=None,
        db=None,
    ):
        self.calls.append(
            {
                "message_type": message_type,
                "message_data": message_data,
                "direction": getattr(direction, "value", direction),
                "host_id": host_id,
                "message_id": message_id,
            }
        )
        return message_id


def _make_host(session, fqdn="host.example.com"):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=fqdn,
        active=True,
        status="up",
        approval_status="approved",
    )
    session.add(host)
    session.flush()
    return host


def _queue_command(session, command_type="reboot", target_host_ids=None):
    cmd = inbox_svc.receive_command(
        session,
        command_id=uuid.uuid4(),
        command_type=command_type,
        parameters={"foo": "bar"},
        target_host_ids=target_host_ids,
    )
    session.flush()
    return cmd


def _sync_rows(session):
    return session.query(FederationSyncQueue).all()


def test_fanout_targets_all_approved_hosts_when_unspecified(session):
    h1 = _make_host(session, "a.example.com")
    h2 = _make_host(session, "b.example.com")
    cmd = _queue_command(session, "reboot", target_host_ids=None)

    qops = FakeQueueOps()
    summary = actuation.fanout_queued_commands(session, queue_ops=qops)

    assert summary == {"dispatched": 1, "messages": 2, "failed": 0}
    assert len(qops.calls) == 2
    targeted = {c["host_id"] for c in qops.calls}
    assert targeted == {str(h1.id), str(h2.id)}
    # All outbound, command type translated, queue id == inner message id.
    for call in qops.calls:
        assert call["direction"] == "outbound"
        assert call["message_type"] == "command"
        assert call["message_data"]["data"]["command_type"] == "reboot_system"
        assert call["message_data"]["message_id"] == call["message_id"]

    refreshed = inbox_svc.get_received_command(session, cmd.id)
    assert refreshed.status == inbox_svc.CMD_STATUS_IN_PROGRESS
    progress = json.loads(refreshed.result_json)
    assert set(progress["target_host_ids"]) == {str(h1.id), str(h2.id)}


def test_fanout_respects_explicit_targets_and_flags_missing(session):
    h1 = _make_host(session, "a.example.com")
    ghost = str(uuid.uuid4())
    cmd = _queue_command(session, "apply_updates", target_host_ids=[str(h1.id), ghost])

    qops = FakeQueueOps()
    actuation.fanout_queued_commands(session, queue_ops=qops)

    # Only the resolvable host gets an agent message.
    assert {c["host_id"] for c in qops.calls} == {str(h1.id)}
    progress = json.loads(inbox_svc.get_received_command(session, cmd.id).result_json)
    assert progress["results"][ghost]["success"] is False


def test_unsupported_command_type_fails_pre_dispatch(session):
    _make_host(session)
    cmd = _queue_command(session, "frobnicate", target_host_ids=None)

    qops = FakeQueueOps()
    summary = actuation.fanout_queued_commands(session, queue_ops=qops)

    assert summary["failed"] == 1
    assert qops.calls == []
    refreshed = inbox_svc.get_received_command(session, cmd.id)
    assert refreshed.status == inbox_svc.CMD_STATUS_FAILED
    # Failure is reported upstream via the sync queue.
    rows = _sync_rows(session)
    assert len(rows) == 1
    assert rows[0].payload_type == "command_result"


def test_all_hosts_success_settles_completed_and_reports_up(session):
    h1 = _make_host(session, "a.example.com")
    h2 = _make_host(session, "b.example.com")
    cmd = _queue_command(session, "reboot", target_host_ids=None)
    actuation.fanout_queued_commands(session, queue_ops=FakeQueueOps())

    actuation.record_command_host_result(session, cmd.id, str(h1.id), success=True)
    # Not terminal until every host reports.
    assert (
        inbox_svc.get_received_command(session, cmd.id).status
        == inbox_svc.CMD_STATUS_IN_PROGRESS
    )
    actuation.record_command_host_result(session, cmd.id, str(h2.id), success=True)

    refreshed = inbox_svc.get_received_command(session, cmd.id)
    assert refreshed.status == inbox_svc.CMD_STATUS_COMPLETED
    rows = _sync_rows(session)
    assert len(rows) == 1
    payload = json.loads(rows[0].payload_json)
    assert payload["command_id"] == str(cmd.id)
    assert payload["status"] == "completed"
    assert payload["success_count"] == 2


def test_any_host_failure_settles_failed(session):
    h1 = _make_host(session, "a.example.com")
    h2 = _make_host(session, "b.example.com")
    cmd = _queue_command(session, "reboot", target_host_ids=None)
    actuation.fanout_queued_commands(session, queue_ops=FakeQueueOps())

    actuation.record_command_host_result(session, cmd.id, str(h1.id), success=True)
    actuation.record_command_host_result(
        session, cmd.id, str(h2.id), success=False, detail="boom"
    )

    refreshed = inbox_svc.get_received_command(session, cmd.id)
    assert refreshed.status == inbox_svc.CMD_STATUS_FAILED
    payload = json.loads(_sync_rows(session)[0].payload_json)
    assert payload["status"] == "failed"
    assert payload["success_count"] == 1


def test_result_is_idempotent_on_replay(session):
    h1 = _make_host(session, "a.example.com")
    cmd = _queue_command(session, "reboot", target_host_ids=[str(h1.id)])
    actuation.fanout_queued_commands(session, queue_ops=FakeQueueOps())

    actuation.record_command_host_result(session, cmd.id, str(h1.id), success=True)
    # Replay after terminal — must not raise or duplicate the sync packet.
    actuation.record_command_host_result(session, cmd.id, str(h1.id), success=True)

    assert (
        inbox_svc.get_received_command(session, cmd.id).status
        == inbox_svc.CMD_STATUS_COMPLETED
    )
    assert len(_sync_rows(session)) == 1


def test_fanout_is_not_reentrant(session):
    _make_host(session)
    _queue_command(session, "reboot", target_host_ids=None)
    actuation.fanout_queued_commands(session, queue_ops=FakeQueueOps())

    # Second tick: the command is in_progress now, not queued — no re-dispatch.
    qops2 = FakeQueueOps()
    summary = actuation.fanout_queued_commands(session, queue_ops=qops2)
    assert summary["dispatched"] == 0
    assert qops2.calls == []
