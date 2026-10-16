# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A late acknowledgment or result closes the command (production, 2026-10-16).

An ``apply_updates`` to a host reconnecting after a server upgrade ran out of
no-ack retries a minute before its acknowledgment arrived; the agent then
reported 11 of 11 updates installed, and the queue row stayed FAILED, so the
UI said the work had failed.  Another command's acknowledgment arrived while
a retry was scheduled, was discarded, and the command was sent -- and run --
again.
"""

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api import message_handlers
from backend.persistence.db import Base
from backend.persistence.models import MessageQueue
from backend.websocket.queue_enums import QueueDirection, QueueStatus
from backend.websocket.queue_operations import QueueOperations

HOST = uuid.uuid4()
OTHER_HOST = uuid.uuid4()
NOW = datetime.utcnow()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[MessageQueue.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _row(
    db,
    status,
    *,
    envelope_id=None,
    host=HOST,
    direction=QueueDirection.OUTBOUND,
    error=None,
    retries=0
):
    row_id = str(uuid.uuid4())
    db.add(
        MessageQueue(
            host_id=host,
            message_id=row_id,
            direction=direction,
            message_type="command",
            message_data=json.dumps(
                {
                    "message_type": "command",
                    "message_id": envelope_id or row_id,
                    "data": {"command_type": "apply_updates"},
                }
            ),
            status=status,
            priority="normal",
            retry_count=retries,
            max_retries=3,
            created_at=NOW - timedelta(minutes=5),
            error_message=error,
        )
    )
    db.commit()
    return row_id


def _get(db, message_id):
    return db.query(MessageQueue).filter_by(message_id=message_id).one()


class TestLateAcknowledgment:
    def test_an_ack_after_the_retries_ran_out_completes_the_command(self, db):
        row = _row(
            db,
            QueueStatus.FAILED,
            retries=3,
            error="No acknowledgment received within 60 seconds",
        )
        assert QueueOperations().mark_acknowledged(row, db=db)
        got = _get(db, row)
        assert got.status == QueueStatus.COMPLETED
        assert got.completed_at is not None
        assert "late acknowledgment (was failed)" in got.error_message
        assert "No acknowledgment received" in got.error_message

    def test_an_ack_while_a_retry_is_scheduled_stops_the_resend(self, db):
        row = _row(db, QueueStatus.PENDING, retries=1)
        assert QueueOperations().mark_acknowledged(row, db=db)
        assert _get(db, row).status == QueueStatus.COMPLETED

    def test_an_inbound_row_is_never_closed_by_an_ack(self, db):
        row = _row(db, QueueStatus.PENDING, direction=QueueDirection.INBOUND)
        assert not QueueOperations().mark_acknowledged(row, db=db)
        assert _get(db, row).status == QueueStatus.PENDING

    def test_a_duplicate_ack_of_finished_work_is_harmless(self, db):
        row = _row(db, QueueStatus.COMPLETED)
        assert QueueOperations().mark_acknowledged(row, db=db)
        assert _get(db, row).error_message is None

    def test_a_resend_in_flight_cannot_reopen_a_completed_command(self, db):
        row = _row(db, QueueStatus.COMPLETED)
        ops = QueueOperations()
        assert ops.mark_sent(row, db=db)
        assert ops.mark_failed(row, error_message="send failed", db=db)
        got = _get(db, row)
        assert got.status == QueueStatus.COMPLETED
        assert got.retry_count == 0 and got.error_message is None


class TestResultClosesTheCommand:
    def test_a_result_matches_the_envelope_id_of_a_failed_command(self, db):
        # apply_updates: the queue row id and the envelope id differ, and the
        # agent echoes the ENVELOPE id as command_id.
        envelope = str(uuid.uuid4())
        row = _row(db, QueueStatus.FAILED, envelope_id=envelope, retries=3)
        assert QueueOperations().complete_on_result(envelope, str(HOST), db)
        got = _get(db, row)
        assert got.status == QueueStatus.COMPLETED
        assert "late result (was failed)" in got.error_message

    def test_a_result_matches_the_row_id_too(self, db):
        row = _row(db, QueueStatus.SENT)
        assert QueueOperations().complete_on_result(row, HOST, db)
        assert _get(db, row).status == QueueStatus.COMPLETED

    def test_another_hosts_command_is_left_alone(self, db):
        envelope = str(uuid.uuid4())
        row = _row(db, QueueStatus.FAILED, envelope_id=envelope, host=OTHER_HOST)
        assert not QueueOperations().complete_on_result(envelope, HOST, db)
        assert _get(db, row).status == QueueStatus.FAILED

    def test_unknown_or_missing_ids_change_nothing(self, db):
        row = _row(db, QueueStatus.FAILED)
        ops = QueueOperations()
        assert not ops.complete_on_result(str(uuid.uuid4()), HOST, db)
        assert not ops.complete_on_result(None, HOST, db)
        assert not ops.complete_on_result(row, None, db)
        assert not ops.complete_on_result(row, "not-a-uuid", db)
        assert _get(db, row).status == QueueStatus.FAILED

    def test_the_result_handler_hook_closes_it_inside_the_callers_transaction(self, db):
        envelope = str(uuid.uuid4())
        row = _row(db, QueueStatus.FAILED, envelope_id=envelope, retries=3)
        message_handlers._close_out_command(
            db, SimpleNamespace(host_id=str(HOST)), envelope
        )
        db.commit()  # the caller's commit
        assert _get(db, row).status == QueueStatus.COMPLETED

    def test_the_hook_never_breaks_result_handling(self, db, monkeypatch):
        from backend.websocket import queue_manager

        def boom(*_a, **_k):
            raise RuntimeError("queue down")

        monkeypatch.setattr(
            queue_manager.server_queue_manager, "complete_on_result", boom
        )
        message_handlers._close_out_command(
            db, SimpleNamespace(host_id=str(HOST)), str(uuid.uuid4())
        )  # does not raise


class TestDisconnectedHostKeepsItsRetries:
    """Right after a server restart agents are still backing off.  A command
    sent then failed, spent a retry each time, and ran out before its host
    reconnected (the droplet's own command: "Failed to send message to agent"
    twice; nas's apply_updates)."""

    @pytest.mark.asyncio
    async def test_a_command_for_a_disconnected_host_waits_without_a_retry(
        self, db, monkeypatch
    ):
        from backend.websocket import outbound_processor as outbound

        row_id = _row(db, QueueStatus.PENDING)
        message = _get(db, row_id)
        sent = []

        async def send(*args, **_kwargs):
            sent.append(args)
            return True

        monkeypatch.setattr(outbound, "_awaiting_poll", lambda host: False)
        monkeypatch.setattr(outbound, "_connected", lambda host: False)
        monkeypatch.setattr(outbound, "send_command_to_agent", send)
        await outbound.process_outbound_message(
            message, SimpleNamespace(id=HOST, fqdn="nas"), db
        )
        db.commit()
        got = _get(db, row_id)
        assert not sent
        assert got.status == QueueStatus.PENDING
        assert got.retry_count == 0
        assert got.scheduled_at is not None and got.scheduled_at > datetime.utcnow()

    def test_connected_matches_the_way_send_to_host_resolves_hosts(self, monkeypatch):
        from backend.websocket import outbound_processor as outbound
        from backend.websocket.connection_manager import connection_manager

        monkeypatch.setattr(connection_manager, "hostname_to_agent", {"NAS": "a1"})
        monkeypatch.setattr(connection_manager, "active_connections", {"a1": object()})
        assert outbound._connected(SimpleNamespace(fqdn="nas"))
        assert not outbound._connected(SimpleNamespace(fqdn="beast"))
        monkeypatch.setattr(connection_manager, "active_connections", {})
        assert not outbound._connected(SimpleNamespace(fqdn="nas"))
