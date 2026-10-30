# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Can a host reach its backup storage?  A host that cannot is not offered
backups (production, 2026-10-30: the server's own droplet and the home NAS);
an unknown answer never blocks."""

# pylint: disable=redefined-outer-name

import json
from datetime import timedelta

import pytest

from backend.api import backups as api
from backend.api import backups_equip as equip_api
from backend.api import backups_setup as setup
from backend.persistence import models
from backend.services import backup_equip
from backend.services import backup_jobs as jobs
from backend.services import backup_reach as reach
from backend.services import backup_tick as tick
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _host,
    _setup,
    sent,
)
from tests.test_backups_api import MANAGER, _status

CAN_CHECK = json.dumps({"capabilities": ["backup", "backup_reach"], "commands": []})
NAS = "192.168.4.10"


def _ready(session):
    s = _setup(session)
    s.nas.ipv4 = NAS
    s.host.agent_capabilities = CAN_CHECK
    session.flush()
    return s


def _answer(session, host, command_id, reachable, error=None, wrapped=False):
    result = {"success": True, "reachable": reachable, "address": NAS,
              "port": 2049, "error": error}  # fmt: skip
    if wrapped:
        result = {"success": True, "result": result}
    assert reach.record_result(session, host.id, {
        "command_id": command_id, "success": True, "result": result})  # fmt: skip
    session.flush()


def _unreachable(session, s, sent):
    command_id = reach.start(session, s.host)
    assert sent[-1][1:] == ("check_backup_storage", {"address": NAS})
    _answer(session, s.host, command_id, False, "timeout")
    return command_id


def test_a_check_asks_only_the_storage_address_and_records_the_answer(session, sent):
    s = _ready(session)
    assert reach.due(session, s.host)
    command_id = reach.start(session, s.host)
    assert sent == [(str(s.host.id), "check_backup_storage", {"address": NAS})]
    assert reach.state(session, s.host) is None  # still checking: unknown
    assert not reach.blocked(session, s.host)
    _answer(session, s.host, command_id, True, wrapped=True)
    assert reach.state(session, s.host)["reachable"] is True
    assert not reach.due(session, s.host)
    assert reach.due(session, s.host, jobs.now() + timedelta(days=1, minutes=1))


def test_an_unreachable_storage_blocks_with_a_plain_message(session, sent):
    s = _ready(session)
    _unreachable(session, s, sent)
    assert reach.blocked(session, s.host)
    text = reach.message(session, s.host)
    assert "nas.lab" in text and NAS in text and "2049" in text


def test_unknown_never_blocks_and_a_moved_storage_host_is_asked_again(session, sent):
    s = _ready(session)
    assert not reach.blocked(session, s.host)  # never checked
    _unreachable(session, s, sent)
    s.nas.ipv4 = "192.168.4.11"
    session.flush()
    assert not reach.blocked(session, s.host) and reach.due(session, s.host)


def test_the_storage_host_and_old_agents_are_never_asked(session, sent):
    s = _ready(session)
    s.nas.agent_capabilities = CAN_CHECK
    assert reach.start(session, s.nas, force=True) is None
    old = _host(session, fqdn="old.lab")
    assert reach.start(session, old, force=True) is None
    assert not sent


def test_an_answer_to_no_check_of_ours_or_no_answer_is_ignored(session, sent):
    s = _ready(session)
    assert not reach.record_result(session, s.host.id, {"command_id": "nope"})
    command_id = reach.start(session, s.host)
    assert not reach.record_result(session, s.nas.id, {"command_id": command_id})
    assert not reach.record_result(session, s.host.id, {
        "command_id": command_id, "success": False,
        "result": {"success": False, "reachable": None, "error": "invalid_address"}})  # fmt: skip


@pytest.mark.asyncio
async def test_policy_backup_now_and_bulk_actions_refuse_an_unreachable_host(
    session, sent
):
    s = _ready(session)
    _unreachable(session, s, sent)
    assert await _status(api.backup_now(str(s.host.id), None, session, MANAGER)) == 409
    check = await api.backup_now(
        str(s.host.id), api.RunBody(action="check"), session, MANAGER
    )
    assert check["host_id"] == str(s.nas.id)  # the storage side still runs
    assert await _status(
        api.put_policy(str(s.host.id), api.PolicyBody(), session, MANAGER)
    ) == 409  # fmt: skip
    answer = await api.bulk_backup_now(
        api.BulkBackupBody(host_ids=[str(s.host.id)]), session, MANAGER
    )
    assert answer["skipped"][0]["reason"] == "storage_unreachable"


@pytest.mark.asyncio
async def test_bulk_setup_and_equip_skip_an_unreachable_host(session, sent):
    s = _ready(session)
    fresh = _host(session, fqdn="fresh.lab", caps=CAN_CHECK)
    command_id = reach.start(session, fresh)
    _answer(session, fresh, command_id, False)
    answer = await setup.bulk_backup_setup(
        setup.BulkSetupBody(host_ids=[str(fresh.id)]), session, MANAGER
    )
    assert answer["skipped"][0]["reason"] == "storage_unreachable"
    bare = _host(session, fqdn="bare.lab", caps=json.dumps(
        {"capabilities": ["backup_equip", "backup_reach"],
         "unavailable": {"backup": "missing_tool"}, "commands": []}))  # fmt: skip
    command_id = reach.start(session, bare)
    _answer(session, bare, command_id, False)
    assert backup_equip.blocker(session, bare) == backup_equip.STORAGE_UNREACHABLE
    assert await _status(equip_api.backup_equip(str(bare.id), session, MANAGER)) == 409
    assert s.host is not None


@pytest.mark.asyncio
async def test_check_again_asks_now(session, sent):
    s = _ready(session)
    _unreachable(session, s, sent)
    answer = await equip_api.backup_reach_check(str(s.host.id), session, MANAGER)
    assert answer["command_id"] and sent[-1][1] == "check_backup_storage"
    old = _host(session, fqdn="old.lab")
    assert (
        await _status(equip_api.backup_reach_check(str(old.id), session, MANAGER))
        == 409
    )


def test_the_tick_asks_due_hosts_once_and_holds_captures_for_unreachable_ones(
    session, sent
):
    s = _ready(session)
    now = jobs.now()
    assert tick.reach_checks(session, now) == 1
    assert tick.reach_checks(session, now) == 0  # asked, not answered yet
    row = session.query(models.BackupReach).filter_by(host_id=s.host.id).one()
    _answer(session, s.host, row.command_id, False)
    s.policy.host_acked_version = s.policy.storage_acked_version = (
        s.policy.config_version
    )
    session.flush()
    sent.clear()
    tick.reconcile(session, now + timedelta(days=3))
    assert not [c for c in sent if c[2].get("action") == "capture"]
