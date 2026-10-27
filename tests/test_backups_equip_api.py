# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Check again: a host installed restate after its agent registered, and read
"not equipped" until the agent restarted (production, 2026-10-25).  The
server now asks the agent for a fresh capability report and keeps it."""

import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from backend.api import backups_equip as equip
from backend.api import message_handlers
from backend.persistence import models
from backend.services import agent_capability_service as capabilities
from backend.services import backup_equip
from backend.services import backup_jobs as jobs
from tests.services.test_backup_results import _setup
from tests.test_backups_api import MANAGER, NOBODY, _status

REPORT = {
    "schema_version": 1,
    "capabilities": ["backup", "diagnostics"],
    "commands": [
        "backup_configure",
        "backup_run",
        "backup_restore",
        "get_capabilities",
    ],
    "unavailable": {},
    "not_applicable": {},
}


@pytest.fixture
def sent():
    calls = []

    def fake(_db, host_id, command_type, parameters):
        calls.append(
            (str(host_id), getattr(command_type, "value", command_type), parameters)
        )
        return str(uuid.uuid4())

    with patch.object(jobs.config_mgmt_dispatch, "queue_command", side_effect=fake):
        yield calls


@pytest.mark.asyncio
async def test_check_again_asks_the_agent_for_its_capabilities(session, sent):
    s = _setup(session)
    answer = await equip.backup_recheck(str(s.host.id), session, MANAGER)
    assert answer["command_id"]
    assert sent[-1][:2] == (str(s.host.id), "get_capabilities")


@pytest.mark.asyncio
async def test_check_again_needs_the_manage_backups_role(session, sent):
    s = _setup(session)
    assert await _status(equip.backup_recheck(str(s.host.id), session, NOBODY)) == 403
    assert (
        await _status(equip.backup_recheck(str(uuid.uuid4()), session, MANAGER)) == 404
    )
    assert sent == []


def _result(success=True, report=None, error=None, empty=False):
    # The agent wraps its handler's {"success", "result": report} as `result`.
    report = None if empty else (report or REPORT)
    return {
        "command_id": str(uuid.uuid4()),
        "success": success,
        "result": {"result": report} if report is not None else None,
        "error": error,
    }


def test_a_fresh_report_replaces_the_stale_one(session):
    s = _setup(session)
    s.host.agent_capabilities = json.dumps({"schema_version": 1, "capabilities": [],
                                            "unavailable": {"backup": "missing_tool"}})  # fmt: skip
    session.commit()
    assert jobs.equipped(s.host) == (False, "missing_tool")
    assert capabilities.record_refresh(session, s.host.id, _result())
    assert jobs.equipped(s.host) == (True, None)


def test_a_refused_or_empty_answer_keeps_what_was_known(session):
    s = _setup(session)
    before = s.host.agent_capabilities
    assert not capabilities.record_refresh(session, s.host.id, _result(success=False))
    assert not capabilities.record_refresh(session, s.host.id, _result(error="boom"))
    assert not capabilities.record_refresh(session, s.host.id, _result(empty=True))
    assert not capabilities.record_refresh(session, uuid.uuid4(), _result())
    assert s.host.agent_capabilities == before


@pytest.mark.asyncio
async def test_the_command_result_is_routed_to_the_refresh(session):
    s = _setup(session)

    class Connection:
        host_id = s.host.id
        hostname = s.host.fqdn

    message = dict(_result(), command_type="get_capabilities")
    with patch.object(capabilities, "record_refresh", return_value=True) as record:
        await message_handlers.handle_command_result(session, Connection(), message)
    record.assert_called_once()


# --- Equip for backup ------------------------------------------------------------

NEEDS_RESTATE = {
    "schema_version": 1,
    "capabilities": ["diagnostics", "backup_equip"],
    "commands": ["equip_backup", "get_capabilities", "backup_configure"],
    "unavailable": {"backup": "missing_tool"},
    "not_applicable": {},
}


def _needs_restate(host, report=None):
    host.agent_capabilities = json.dumps(report or NEEDS_RESTATE)


@pytest.mark.asyncio
async def test_equip_asks_the_agent_to_install_restate(session, sent):
    s = _setup(session)
    _needs_restate(s.host)
    answer = await equip.backup_equip(str(s.host.id), session, MANAGER)
    assert sent[-1][:2] == (str(s.host.id), "equip_backup")
    assert sent[-1][2] == {}  # nothing but the request: the agent decides how
    assert answer["equip"]["status"] == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "report,code",
    [
        (None, "equipped"),  # _setup's host can already back up
        ({**NEEDS_RESTATE, "capabilities": ["diagnostics"]}, "agent_outdated"),
        ({**NEEDS_RESTATE, "capabilities": ["diagnostics"],
          "not_applicable": {"backup_equip": "wrong_platform"}}, "not_applicable"),
    ],
)  # fmt: skip
async def test_equip_says_why_it_cannot_start(session, sent, report, code):
    s = _setup(session)
    if report is not None:
        _needs_restate(s.host, report)
    assert backup_equip.blocker(session, s.host) == code
    assert await _status(equip.backup_equip(str(s.host.id), session, MANAGER)) == 409
    assert await _status(equip.backup_equip(str(s.host.id), session, NOBODY)) == 403
    assert sent == []


@pytest.mark.asyncio
async def test_one_equip_at_a_time_until_it_goes_stale(session, sent):
    s = _setup(session)
    _needs_restate(s.host)
    await equip.backup_equip(str(s.host.id), session, MANAGER)
    assert backup_equip.blocker(session, s.host) == "in_progress"
    later = jobs.now() + backup_equip.STALE_AFTER + timedelta(minutes=1)
    assert backup_equip.state(session, s.host.id, later)["reason"] == "no_answer"
    assert backup_equip.blocker(session, s.host, later) is None


def _queue_row(session, host_id, command_id, status="pending", started_at=None,
               error_message=None):  # fmt: skip
    row = models.MessageQueue(
        host_id=host_id, message_id=command_id, direction="outbound",
        message_type="command", message_data="{}", status=status,
        priority="normal", created_at=jobs.now(), started_at=started_at,
        error_message=error_message,
    )  # fmt: skip
    session.add(row)
    session.flush()
    return row


@pytest.mark.asyncio
async def test_the_hour_to_answer_starts_when_the_command_is_sent(session, sent):
    """Held behind a maintenance window, an install is never "no answer";
    once sent, it has an hour from then (Bryan 2026-10-27)."""
    from backend.services.maintenance_window_service import (  # noqa: PLC0415
        DEFERRED_MARKER,
    )

    s = _setup(session)
    _needs_restate(s.host)
    answer = await equip.backup_equip(str(s.host.id), session, MANAGER)
    queued = _queue_row(session, s.host.id, answer["command_id"],
                        error_message=DEFERRED_MARKER)  # fmt: skip
    days_later = jobs.now() + timedelta(days=3)
    held = backup_equip.state(session, s.host.id, days_later)
    assert held["status"] == "running" and held["held"] is True
    assert backup_equip.blocker(session, s.host, days_later) == "in_progress"

    queued.status, queued.error_message = "sent", None
    queued.started_at = days_later
    sent_state = backup_equip.state(
        session, s.host.id, days_later + timedelta(minutes=5)
    )
    assert sent_state["status"] == "running" and sent_state["held"] is False
    stale = days_later + backup_equip.STALE_AFTER + timedelta(minutes=1)
    assert backup_equip.state(session, s.host.id, stale)["reason"] == "no_answer"


@pytest.mark.asyncio
async def test_a_command_waiting_for_an_offline_agent_does_not_go_stale(session, sent):
    s = _setup(session)
    _needs_restate(s.host)
    answer = await equip.backup_equip(str(s.host.id), session, MANAGER)
    _queue_row(session, s.host.id, answer["command_id"])
    later = jobs.now() + timedelta(days=1)
    state = backup_equip.state(session, s.host.id, later)
    assert state["status"] == "running" and state["held"] is False


@pytest.mark.asyncio
async def test_a_command_that_expired_unsent_counts_from_the_request(session, sent):
    s = _setup(session)
    _needs_restate(s.host)
    answer = await equip.backup_equip(str(s.host.id), session, MANAGER)
    _queue_row(session, s.host.id, answer["command_id"], status="expired")
    later = jobs.now() + backup_equip.STALE_AFTER + timedelta(minutes=1)
    assert backup_equip.state(session, s.host.id, later)["reason"] == "no_answer"


def _equip_result(command_id, success=True, **outcome):
    return {"command_id": command_id, "success": success, "error": None,
            "result": outcome or None}  # fmt: skip


@pytest.mark.asyncio
async def test_a_good_install_asks_for_a_fresh_capability_report(session, sent):
    s = _setup(session)
    _needs_restate(s.host)
    command_id = (await equip.backup_equip(str(s.host.id), session, MANAGER))[
        "command_id"
    ]
    assert backup_equip.record_result(
        session, s.host.id, _equip_result(command_id, installed="2.2.0.6")
    )
    state = backup_equip.state(session, s.host.id)
    assert (state["status"], state["installed"]) == ("ok", "2.2.0.6")
    assert sent[-1][:2] == (str(s.host.id), "get_capabilities")


@pytest.mark.asyncio
async def test_a_failed_install_keeps_the_reason_and_output(session, sent):
    s = _setup(session)
    _needs_restate(s.host)
    command_id = (await equip.backup_equip(str(s.host.id), session, MANAGER))[
        "command_id"
    ]
    backup_equip.record_result(session, s.host.id, _equip_result(
        command_id, success=False, reason="checksum_mismatch", detail="restate-x.pkg"))  # fmt: skip
    state = backup_equip.state(session, s.host.id)
    assert (state["status"], state["reason"]) == ("failed", "checksum_mismatch")
    assert state["detail"] == "restate-x.pkg"
    assert backup_equip.blocker(session, s.host) is None  # may try again


@pytest.mark.asyncio
async def test_a_result_from_another_host_or_command_is_ignored(session, sent):
    s = _setup(session)
    _needs_restate(s.host)
    command_id = (await equip.backup_equip(str(s.host.id), session, MANAGER))[
        "command_id"
    ]
    assert not backup_equip.record_result(session, s.nas.id, _equip_result(command_id))
    assert not backup_equip.record_result(session, s.host.id, _equip_result("x"))
    assert backup_equip.state(session, s.host.id)["status"] == "running"


@pytest.mark.asyncio
async def test_bulk_equip_starts_what_it_can_and_says_why_not(session, sent):
    s = _setup(session)
    _needs_restate(s.host)
    answer = await equip.bulk_backup_equip(
        equip.BulkEquipBody(host_ids=[str(s.host.id), str(s.nas.id), str(uuid.uuid4())]),
        session, MANAGER,
    )  # fmt: skip
    assert answer["started"] == 1
    assert sorted(x["reason"] for x in answer["skipped"]) == ["equipped", "no_host"]


@pytest.mark.asyncio
async def test_the_equip_result_is_routed_to_its_handler(session):
    s = _setup(session)

    class Connection:
        host_id = s.host.id
        hostname = s.host.fqdn

    message = {"command_id": "c", "command_type": "equip_backup", "success": True}
    with patch.object(backup_equip, "record_result", return_value=True) as record:
        await message_handlers.handle_command_result(session, Connection(), message)
    record.assert_called_once()


def test_the_host_row_carries_the_equip_state(session):
    from backend.services import backup_views as views  # noqa: PLC0415

    s = _setup(session)
    _needs_restate(s.host)
    row = views.host_status(session, s.host)
    assert row["equipped"] is False and row["equip"] is None
    assert row["equip_blocker"] is None  # Equip for backup is offered
    assert models.BackupEquip.__tablename__ == "backup_equip"
