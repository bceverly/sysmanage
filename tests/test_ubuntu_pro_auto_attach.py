# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic Ubuntu Pro attach (2026-11-13): the setting was stored but
nothing read it, so new Ubuntu hosts were never attached."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from backend.api.handlers.os_hardware_handlers import handle_ubuntu_pro_update
from backend.persistence import models
from backend.services import ubuntu_pro_auto_attach

HOST_ID = "550e8400-e29b-41d4-a716-4466554400ab"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def host(session):
    row = models.Host(
        id=HOST_ID,
        fqdn="pro-host.example.com",
        ipv4="192.168.1.78",
        active=True,
        platform="Ubuntu",
        platform_release="24.04",
        approval_status="approved",
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def queued(monkeypatch):
    sent = []
    monkeypatch.setattr(
        ubuntu_pro_auto_attach.queue_ops,
        "enqueue_message",
        lambda **kw: sent.append(kw),
    )
    return sent


def _settings(session, auto=True, key="C1234"):
    session.add(
        models.UbuntuProSettings(
            organization_name="Example",
            master_key=key,
            auto_attach_enabled=auto,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    session.commit()


def _report(attached):
    return {"os_info": {"ubuntu_pro": {"attached": attached, "services": []}}}


@pytest.mark.asyncio
async def test_an_unattached_host_is_attached_once_with_the_master_key(
    session, host, queued
):
    _settings(session)
    await handle_ubuntu_pro_update(session, Mock(), _report(False), host)
    assert len(queued) == 1
    command = queued[0]["message_data"]
    assert command["data"]["command_type"] == "ubuntu_pro_attach"
    assert command["data"]["parameters"] == {
        "token": "C1234",
        "organization": "Example",
    }
    assert queued[0]["host_id"] == host.id
    assert host.ubuntu_pro_auto_attach_at is not None

    # Still unattached on the next report (the attach failed): no loop.
    await handle_ubuntu_pro_update(session, Mock(), _report(False), host)
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_a_host_seen_attached_is_never_attached_again_after_a_detach(
    session, host, queued
):
    _settings(session)
    await handle_ubuntu_pro_update(session, Mock(), _report(True), host)
    assert host.ubuntu_pro_auto_attach_at is not None
    await handle_ubuntu_pro_update(session, Mock(), _report(False), host)
    assert not queued


@pytest.mark.asyncio
@pytest.mark.parametrize("auto,key", [(False, "C1234"), (True, None)])
async def test_nothing_is_sent_without_auto_attach_and_a_key(
    session, host, queued, auto, key
):
    _settings(session, auto=auto, key=key)
    await handle_ubuntu_pro_update(session, Mock(), _report(False), host)
    assert not queued
    assert host.ubuntu_pro_auto_attach_at is None  # turning it on later works


@pytest.mark.asyncio
async def test_nothing_is_sent_without_settings(session, host, queued):
    await handle_ubuntu_pro_update(session, Mock(), _report(False), host)
    assert not queued


@pytest.mark.asyncio
async def test_a_host_not_yet_approved_waits(session, host, queued):
    _settings(session)
    host.approval_status = "pending"
    session.commit()
    await handle_ubuntu_pro_update(session, Mock(), _report(False), host)
    assert not queued and host.ubuntu_pro_auto_attach_at is None
