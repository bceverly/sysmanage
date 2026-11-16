# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""An agent that comes back on a new version is asked for its updates, so
the update it just installed leaves the Updates page (production,
2026-11-16)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.api.message_handlers_core import handle_heartbeat
from backend.persistence import models
from backend.services import agent_version_change


def _host(session, version="3.13.0.20", approval="approved"):
    host = models.Host(
        fqdn="ubiquiti",
        ipv4="192.168.4.20",
        active=True,
        status="up",
        approval_status=approval,
        agent_version=version,
    )
    session.add(host)
    session.commit()
    return host


def _checks_queued(session, host):
    rows = (
        session.query(models.MessageQueue)
        .filter(models.MessageQueue.host_id == host.id)
        .all()
    )
    return [
        r
        for r in rows
        if json.loads(r.message_data).get("data", {}).get("command_type")
        == "check_updates"
    ]


def test_a_new_version_queues_an_update_check(session):
    host = _host(session)
    assert agent_version_change.note_agent_version(session, host, "3.13.0.21")
    session.commit()
    assert host.agent_version == "3.13.0.21"
    queued = _checks_queued(session, host)
    assert len(queued) == 1 and queued[0].direction == "outbound"


@pytest.mark.parametrize(
    "stored, reported, approval",
    [
        ("3.13.0.21", "3.13.0.21", "approved"),  # the same version again
        (None, "3.13.0.21", "approved"),  # the first report: startup covers it
        ("3.13.0.20", "3.13.0.21", "pending"),  # not approved
        ("3.13.0.20", None, "approved"),  # no version in this heartbeat
    ],
)
def test_no_check_otherwise(session, stored, reported, approval):
    host = _host(session, stored, approval)
    assert not agent_version_change.note_agent_version(session, host, reported)
    session.commit()
    assert not _checks_queued(session, host)
    assert host.agent_version == (reported or stored)


@pytest.mark.asyncio
async def test_the_heartbeat_after_an_upgrade_queues_one_check(
    session, mock_connection
):
    host = _host(session)
    mock_connection.host_id = host.id
    mock_connection.hostname = host.fqdn
    mock_connection.send_message = AsyncMock()
    with patch(
        "backend.utils.host_validation.validate_host_id",
        new_callable=AsyncMock,
        return_value=True,
    ):
        for _ in range(2):  # the second heartbeat repeats the new version
            await handle_heartbeat(
                session, mock_connection, {"agent_version": "3.13.0.21"}
            )
    session.expire_all()
    assert session.get(models.Host, host.id).agent_version == "3.13.0.21"
    assert len(_checks_queued(session, host)) == 1
