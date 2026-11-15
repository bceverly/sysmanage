# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Agent lost during its own upgrade (2026-11-15): derived from the update
log and the outbound queue, shown on the host API."""

# pylint: disable=redefined-outer-name

import json
import uuid
from datetime import datetime, timedelta

import pytest

from backend.api import host as host_api
from backend.persistence import models
from backend.services import agent_self_update_loss as loss

SENT_AT = datetime(2026, 11, 15, 9, 0, 0)


@pytest.fixture(autouse=True)
def _five_minute_timeout(monkeypatch):
    monkeypatch.setattr(loss, "get_heartbeat_timeout_minutes", lambda: 5)


def _host(session, status="down", seen=SENT_AT + timedelta(seconds=20)):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"h-{uuid.uuid4().hex[:8]}.lab",
        active=status == "up",
        approval_status="approved",
        status=status,
        last_access=seen,
    )
    session.add(host)
    session.commit()
    return host


def _logged(session, host, package="sysmanage-agent", at=SENT_AT, manager="apt"):
    session.add(
        models.UpdateExecutionLog(
            host_id=host.id,
            package_name=package,
            package_manager=manager,
            from_version="3.14.0.1",
            to_version="3.14.0.2",
            execution_status="pending",
            created_at=at,
            updated_at=at,
        )
    )
    session.commit()


def _queued(session, host, packages, at=SENT_AT, status="completed"):
    data = {
        "message_type": "command",
        "message_id": str(uuid.uuid4()),
        "data": {
            "command_type": "apply_updates",
            "parameters": {"packages": packages},
        },
    }
    session.add(
        models.MessageQueue(
            host_id=host.id,
            message_id=str(uuid.uuid4()),
            direction="outbound",
            message_type="command",
            message_data=json.dumps(data),
            status=status,
            priority="normal",
            created_at=at,
        )
    )
    session.commit()


def _pkg(name, manager="dnf"):
    return {"package_name": name, "package_manager": manager}


def test_down_after_its_own_upgrade_is_lost(session):
    host = _host(session)
    _logged(session, host)
    assert loss.lost_hosts(session, [host]) == {host.id: (SENT_AT, "apt")}
    shown = host_api._self_update_fields(session, host)
    assert shown == {
        "agent_lost_in_self_update": True,
        "agent_self_update_dispatched_at": "2026-11-15T09:00:00+00:00",
        "agent_self_update_package_manager": "apt",
    }


def test_last_check_in_just_before_the_dispatch_counts(session):
    host = _host(session, seen=SENT_AT - timedelta(minutes=1))
    _logged(session, host)
    assert host.id in loss.lost_hosts(session, [host])


def test_a_queued_dispatch_from_any_path_counts(session):
    host = _host(session)
    _queued(session, host, [_pkg("curl"), _pkg("sysmanage-agent")])
    assert loss.lost_hosts(session, [host]) == {host.id: (SENT_AT, "dnf")}


def test_other_platform_names_are_the_agent(session):
    for name in ("SysManage Agent", "com.sysmanage.agent", "sysmanage-agent-strict"):
        assert loss.is_agent_package(name)
    assert not loss.is_agent_package("sysmanage")
    assert not loss.is_agent_package(None)
    host = _host(session)
    _logged(session, host, package="SysManage Agent", manager="winget")
    assert host.id in loss.lost_hosts(session, [host])


def test_checked_in_after_the_update_is_not_lost(session):
    host = _host(session, seen=SENT_AT + timedelta(hours=2))
    _logged(session, host)
    _queued(session, host, [_pkg("sysmanage-agent")])
    assert not loss.lost_hosts(session, [host])
    shown = host_api._self_update_fields(session, host)
    assert shown["agent_lost_in_self_update"] is False


def test_an_update_without_the_agent_is_not_lost(session):
    host = _host(session)
    _logged(session, host, package="openssl")
    _queued(session, host, [_pkg("curl")])
    assert not loss.lost_hosts(session, [host])


def test_an_up_host_is_not_lost(session):
    host = _host(session, status="up")
    _logged(session, host)
    assert not loss.lost_hosts(session, [host])


def test_already_down_when_sent_is_not_lost(session):
    host = _host(session, seen=SENT_AT - timedelta(days=1))
    _logged(session, host)
    _queued(session, host, [_pkg("sysmanage-agent")], status="pending")
    assert not loss.lost_hosts(session, [host])


def test_an_undelivered_command_does_not_count(session):
    host = _host(session)
    _queued(session, host, [_pkg("sysmanage-agent")], status="pending")
    assert not loss.lost_hosts(session, [host])


def test_a_retry_after_it_went_down_does_not_hide_the_loss(session):
    host = _host(session)
    _logged(session, host)
    _logged(session, host, at=SENT_AT + timedelta(hours=1), manager="apt")
    assert loss.lost_hosts(session, [host]) == {host.id: (SENT_AT, "apt")}


def test_garbage_queue_payloads_are_ignored(session):
    assert loss._agent_package_manager("not json") == (False, None)
    assert loss._agent_package_manager('"apply_updates"') == (False, None)
    assert loss._agent_package_manager(
        json.dumps({"data": {"command_type": "reboot"}})
    ) == (False, None)


def test_a_failed_query_never_breaks_the_host_list(session, monkeypatch):
    host = _host(session)

    def _boom(*_args):
        raise RuntimeError("database gone")

    monkeypatch.setattr(loss, "_logged_dispatches", _boom)
    assert not loss.lost_hosts(session, [host])
    assert loss.fields(None) == {
        "agent_lost_in_self_update": False,
        "agent_self_update_dispatched_at": None,
        "agent_self_update_package_manager": None,
    }
