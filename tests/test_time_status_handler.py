# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What a host's time service claims (Phase 23.3 S2)."""

import asyncio
import uuid
from types import SimpleNamespace

from backend.api.handlers.time_status_handlers import handle_time_status_update
from backend.persistence import models


def _host(session):
    host = models.Host(
        id=uuid.uuid4(), fqdn="beast.lab", active=True, approval_status="approved"
    )
    session.add(host)
    session.commit()
    return host


def _send(session, host_id, payload):
    return asyncio.run(
        handle_time_status_update(
            session, SimpleNamespace(host_id=host_id), {"data": payload}
        )
    )


def test_the_claim_is_stored(session):
    host = _host(session)
    result = _send(
        session,
        host.id,
        {
            "service": "chrony",
            "running": True,
            "synchronized": True,
            "source": "  ntp.lab  ",
            "stratum": 2,
            "reported_offset_ms": -0.4,
        },
    )
    assert result == {"message_type": "time_status_ack"}
    session.refresh(host)
    assert (host.time_service, host.time_source, host.time_stratum) == (
        "chrony",
        "ntp.lab",
        2,
    )
    assert host.time_synchronized is True
    assert host.time_reported_offset_ms == -0.4
    assert host.time_status_at is not None


def test_unknown_or_mistyped_fields_are_not_guessed(session):
    host = _host(session)
    _send(
        session,
        host.id,
        {
            "service": "sundial",
            "running": "yes",
            "synchronized": 1,
            "source": 7,
            "stratum": True,
            "reported_offset_ms": "3",
        },
    )
    session.refresh(host)
    assert host.time_service is None
    assert host.time_service_running is None
    assert host.time_synchronized is None
    assert host.time_source is None
    assert host.time_stratum is None
    assert host.time_reported_offset_ms is None


def test_a_flat_message_and_a_stopped_service(session):
    host = _host(session)
    asyncio.run(
        handle_time_status_update(
            session,
            SimpleNamespace(host_id=host.id),
            {"service": "w32time", "running": False, "reported_offset_ms": 12},
        )
    )
    session.refresh(host)
    assert (host.time_service, host.time_service_running) == ("w32time", False)
    assert host.time_reported_offset_ms == 12.0


def test_no_or_unknown_host_is_refused(session):
    for host_id in (None, uuid.uuid4()):
        result = _send(session, host_id, {"service": "ntpd"})
        assert result["error_type"] == "host_not_registered"
