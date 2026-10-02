# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: per-message CPU in the inbound path.

A py-spy profile at 2,000 agents: inventory ingestion 24% of the drain (one
ORM object per package), status bookkeeping 12%, re-validating hosts the drain
had just loaded 5%, and queueing on the event loop 41% of its time.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from backend.api.handlers.software_package_handlers import handle_software_update
from backend.persistence.models import Host, MessageQueue, SoftwarePackage
from backend.utils.host_validation import validate_host_id
from backend.websocket.queue_manager import (
    QueueDirection,
    QueueStatus,
    server_queue_manager,
)


def _host(session):
    host = Host(id=uuid4(), fqdn=f"{uuid4().hex[:8]}.example.com", active=True,
                approval_status="approved")  # fmt: skip
    session.add(host)
    session.commit()
    return host


def _packages(names):
    return [
        {"package_name": n, "version": "1.0", "package_manager": "apt"} for n in names
    ]


async def test_an_inventory_replaces_the_last_one_in_bulk(session):
    host = _host(session)
    conn = SimpleNamespace(host_id=host.id, verified_host_id=str(host.id))
    await handle_software_update(session, conn, {"host_id": str(host.id),
                                                 "software_packages": _packages(["a", "b"])})  # fmt: skip
    await handle_software_update(session, conn, {"host_id": str(host.id),
                                                 "software_packages": _packages(["c", "d", "e"])})  # fmt: skip
    session.expire_all()
    rows = session.query(SoftwarePackage).filter_by(host_id=host.id).all()
    assert sorted(r.package_name for r in rows) == ["c", "d", "e"]
    assert all(r.id is not None and r.is_system_package is False for r in rows)
    assert session.get(Host, host.id).software_updated_at is not None


async def test_the_drain_host_is_not_validated_again(session):
    host_id = str(uuid4())  # not in the database: a real lookup would fail
    conn = SimpleNamespace(verified_host_id=host_id, send_message=AsyncMock())
    assert await validate_host_id(session, conn, host_id) is True
    conn.send_message.assert_not_awaited()


async def test_any_other_host_is_still_validated(session):
    conn = SimpleNamespace(verified_host_id=str(uuid4()), send_message=AsyncMock())
    with patch("backend.utils.host_validation._host_exists_in_other_partition",return_value=False):  # fmt: skip
        assert await validate_host_id(session, conn, str(uuid4())) is False


def test_completion_is_one_update(session):
    host = _host(session)
    message = MessageQueue(
        message_id=str(uuid4()), host_id=host.id, direction=QueueDirection.INBOUND,
        status=QueueStatus.IN_PROGRESS, priority="normal", message_type="x",
        message_data="{}", created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )  # fmt: skip
    session.add(message)
    session.commit()
    assert server_queue_manager.mark_completed(message.message_id, db=session)
    session.commit()
    session.expire_all()
    row = session.query(MessageQueue).filter_by(message_id=message.message_id).one()
    assert row.status == QueueStatus.COMPLETED and row.completed_at is not None
    assert not server_queue_manager.mark_completed("no-such", db=session)
