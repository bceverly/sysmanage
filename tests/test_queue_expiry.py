# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: queue expiry that does not punish waiting.

Inbound messages used to expire 60 minutes after they were CREATED, so any
backlog turned into silent data loss -- agent reports thrown away because the
server was busy.  Now an inbound message expires on time since its last
ATTEMPT (it keeps failing), or past a hard ceiling (default 24 h).  Outbound
keeps age-based expiry on purpose: a command delivered an hour late is worse
than one never delivered.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.persistence.models import Host, MessageQueue
from backend.websocket.queue_manager import (
    QueueDirection,
    QueueStatus,
    server_queue_manager,
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host(session):
    host = Host(id=str(uuid4()), fqdn=f"{uuid4().hex[:8]}.example.com", active=True,
                approval_status="approved")  # fmt: skip
    session.add(host)
    session.commit()
    return host


def _message(session, host, direction, created, attempted=None):
    message = MessageQueue(
        message_id=str(uuid4()), host_id=host.id, direction=direction,
        status=QueueStatus.PENDING, priority="normal", message_type="test_message",
        message_data="{}", created_at=created, started_at=attempted,
        last_error_at=attempted,
    )  # fmt: skip
    session.add(message)
    session.commit()
    return message.message_id


def _expired(session, message_id):
    session.expire_all()
    row = session.query(MessageQueue).filter_by(message_id=message_id).first()
    return row.expired_at is not None


def test_an_inbound_message_that_only_waited_is_kept(session):
    host = _host(session)
    waited = _message(
        session, host, QueueDirection.INBOUND, _now() - timedelta(minutes=90)
    )
    server_queue_manager.expire_old_messages(session)
    assert not _expired(session, waited)


def test_an_inbound_message_still_failing_after_the_timeout_expires(session):
    host = _host(session)
    stale = _now() - timedelta(minutes=90)
    failing = _message(session, host, QueueDirection.INBOUND, stale, attempted=stale)
    server_queue_manager.expire_old_messages(session)
    assert _expired(session, failing)


def test_a_recent_attempt_keeps_an_old_inbound_message(session):
    host = _host(session)
    retried = _message(session, host, QueueDirection.INBOUND,
                       _now() - timedelta(minutes=90), attempted=_now() - timedelta(minutes=5))  # fmt: skip
    server_queue_manager.expire_old_messages(session)
    assert not _expired(session, retried)


def test_the_hard_ceiling_still_bounds_a_backlog(session):
    host = _host(session)
    ancient = _message(
        session, host, QueueDirection.INBOUND, _now() - timedelta(hours=25)
    )
    server_queue_manager.expire_old_messages(session)
    assert _expired(session, ancient)


def test_outbound_keeps_age_based_expiry(session):
    host = _host(session)
    late = _message(
        session, host, QueueDirection.OUTBOUND, _now() - timedelta(minutes=90)
    )
    server_queue_manager.expire_old_messages(session)
    assert _expired(session, late)
