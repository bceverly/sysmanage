# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""End-to-end integration test for the Phase 13.1 tenant-enrollment data plane.

Every seam of the enrollment chain is unit-tested in isolation / inert mode
elsewhere; this exercises the WHOLE chain with multi-tenancy "on", proving the
pieces compose:

  enrollment-token register  ->  host row lands in the TENANT database
                             ->  host->tenant binding recorded
                             ->  the queue processor (running on the tenant DB)
                                 FINDS the host and does NOT delete its messages
  SYSTEM_INFO (with host_id)  ->  routes to the tenant DB, updating the SAME
                                  host (no duplicate row in the bootstrap DB)

No compiled Pro+ engine is required: the licensed seam (tenant-engine
resolution, host<->tenant index, token validation) is monkeypatched onto a
second real in-memory database, so this runs in OSS CI.
"""

# pylint: disable=redefined-outer-name

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import config
from backend.persistence import partitions
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.db import Base
from backend.services import enrollment_service, host_tenant_index
from backend.websocket import inbound_processor
from backend.websocket.queue_enums import QueueDirection, QueueStatus

TOKEN = "sme_e2e_token"  # nosec B105 - test fixture token, not a real secret
TENANT_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def tenant_engine():
    """A second real DB standing in for the enrolling tenant's database."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def mt_chain(
    engine, tenant_engine, monkeypatch
):  # noqa: ARG001 - engine sets bootstrap
    """Wire the licensed seam so MT routing sends tenant data to ``tenant_engine``
    while everything else stays on the bootstrap engine (the root ``engine``
    fixture).  Returns the tenant engine + the in-memory host->tenant index."""
    bindings = {}  # host_id -> tenant_id

    monkeypatch.setattr(config, "is_multitenancy_enabled", lambda: True)

    def fake_resolve(partition=partitions.PARTITION_TENANT, tenant_id=None):
        if partition == partitions.PARTITION_TENANT and tenant_id is not None:
            return tenant_engine
        return db_module.get_engine()

    monkeypatch.setattr(partitions, "resolve_engine", fake_resolve)
    monkeypatch.setattr(
        host_tenant_index,
        "bind_host_to_tenant",
        lambda host_id, tenant_id: bindings.__setitem__(str(host_id), str(tenant_id))
        or True,
    )
    monkeypatch.setattr(
        host_tenant_index,
        "tenant_for_host",
        lambda host_id: bindings.get(str(host_id)),
    )
    monkeypatch.setattr(
        enrollment_service,
        "validate_and_consume",
        lambda session, token: TENANT_ID if token == TOKEN else None,
    )

    return {"tenant_engine": tenant_engine, "bindings": bindings}


def _register(fqdn="agent1.example.com", token=TOKEN):
    """Drive the real /host/register handler and return the created Host."""
    from backend.api.host import HostRegistration, register_host

    reg = HostRegistration(
        active=True,
        fqdn=fqdn,
        hostname=fqdn.split(".", maxsplit=1)[0],
        ipv4="10.0.0.1",
        enrollment_token=token,
    )
    return asyncio.run(register_host(reg))


def _count_hosts(eng, fqdn):
    with sessionmaker(bind=eng)() as session:
        return session.query(models.Host).filter(models.Host.fqdn == fqdn).count()


class TestTenantEnrollmentEndToEnd:
    """The full enrollment chain with multi-tenancy enabled."""

    def test_register_creates_host_in_tenant_db_not_bootstrap(self, mt_chain):
        """A token registration lands the host in the tenant DB (not bootstrap)
        and records the host->tenant binding."""
        host = _register()
        host_id = str(host.id)

        assert _count_hosts(mt_chain["tenant_engine"], "agent1.example.com") == 1
        assert _count_hosts(db_module.get_engine(), "agent1.example.com") == 0
        assert mt_chain["bindings"][host_id] == TENANT_ID

    def test_no_token_stays_on_bootstrap(self, mt_chain):
        """Without a token the host is server-scoped: bootstrap DB, no binding."""
        host = _register(fqdn="server1.example.com", token=None)

        assert _count_hosts(db_module.get_engine(), "server1.example.com") == 1
        assert _count_hosts(mt_chain["tenant_engine"], "server1.example.com") == 0
        assert str(host.id) not in mt_chain["bindings"]

    def test_tenant_engine_for_host_routes_to_tenant(self, mt_chain):
        """The processor's routing resolver sends a bound host to its tenant
        engine, and an unbound host to the default (None)."""
        _register()
        host_id = next(iter(mt_chain["bindings"]))

        assert partitions.tenant_engine_for_host(host_id) is mt_chain["tenant_engine"]
        assert partitions.tenant_engine_for_host(str(uuid.uuid4())) is None

    def test_processor_finds_tenant_host_and_does_not_delete(self, mt_chain):
        """The crux of #2: a message queued in the tenant DB is processed by the
        processor (host found there), NOT hard-deleted as 'host gone'."""
        host = _register()
        host_id = host.id

        # Approve the host in the tenant DB (an admin would do this) so the
        # processor takes the process path, not the unapproved-drop policy.
        with sessionmaker(bind=mt_chain["tenant_engine"])() as ts:
            row = ts.query(models.Host).filter(models.Host.id == host_id).first()
            row.approval_status = "approved"
            ts.commit()

        # Queue an inbound message for the host IN THE TENANT DB.
        with sessionmaker(bind=mt_chain["tenant_engine"])() as ts:
            ts.add(
                models.MessageQueue(
                    message_id=str(uuid.uuid4()),
                    host_id=host_id,
                    direction=QueueDirection.INBOUND,
                    status=QueueStatus.PENDING,
                    message_type="heartbeat",
                    message_data=json.dumps({"hostname": "agent1.example.com"}),
                    priority="normal",
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            ts.commit()

        with patch.object(
            inbound_processor, "process_validated_message", new=AsyncMock()
        ) as mock_process, patch.object(
            inbound_processor.server_queue_manager, "delete_messages_for_host"
        ) as mock_delete:
            with sessionmaker(bind=mt_chain["tenant_engine"])() as ts:
                asyncio.run(inbound_processor.process_pending_messages(ts))

        # Host was found in the tenant DB -> message processed, NOT deleted.
        mock_process.assert_called()
        mock_delete.assert_not_called()

    def test_system_info_routes_to_tenant_no_duplicate(self, mt_chain):
        """SYSTEM_INFO carrying the agent's host_id routes to the tenant DB and
        updates the SAME host — no duplicate row appears in the bootstrap DB."""
        from backend.api.message_handlers_core import handle_system_info

        host = _register()
        host_id = str(host.id)

        message = {
            "host_id": host_id,
            "hostname": "agent1.example.com",
            "ipv4": "10.0.0.9",
            "platform": "Linux",
        }
        connection = MagicMock()
        connection.is_mock_connection = True

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new=AsyncMock(return_value=True),
        ):
            # The inbound ``db`` is the bootstrap session; the wrapper must
            # re-route to the tenant DB off the host_id.
            with sessionmaker(bind=db_module.get_engine())() as bootstrap_db:
                asyncio.run(handle_system_info(bootstrap_db, connection, message))

        assert _count_hosts(mt_chain["tenant_engine"], "agent1.example.com") == 1
        assert _count_hosts(db_module.get_engine(), "agent1.example.com") == 0
