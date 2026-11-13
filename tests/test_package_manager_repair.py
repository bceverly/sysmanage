# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Package manager needs repair (2026-11-13): stored from the agent's update
scan, flagged on the host, repaired on request, and the migration."""

# pylint: disable=redefined-outer-name,unused-argument

import json
import os
import tempfile

import pytest

from backend.api import package_manager_repair as api
from backend.security.roles import SecurityRoles
from backend.services import package_manager_repair as repair
from tests.services.test_backup_results import _host, _setup  # noqa: F401
from tests.test_backup_proxy_migration import _columns
from tests.test_backup_rules_migration import _alembic
from tests.test_backups_api import NOBODY, _status, _user  # noqa: F401
from tests.services.test_backup_results import (
    sent,
)  # noqa: F401  pylint: disable=unused-import

PATCHER = _user(SecurityRoles.APPLY_SOFTWARE_UPDATE)

BROKEN = {"manager": "dpkg", "needs_repair": True, "repairable": True,
          "reason": "dpkg was interrupted"}  # fmt: skip


def _able(host):
    host.agent_capabilities = json.dumps({"capabilities": [repair.GROUP]})


def test_the_scan_sets_and_clears_the_flag(session):
    s = _setup(session)
    assert repair.store(s.host, BROKEN) is True
    assert s.host.package_manager_needs_repair and s.host.package_manager_repairable
    assert s.host.package_manager_repair_reason == "dpkg was interrupted"
    assert repair.store(
        s.host, {"manager": "dpkg", "needs_repair": False, "repairable": True}
    )
    assert (
        not s.host.package_manager_needs_repair
        and s.host.package_manager_repair_reason is None
    )
    # An older agent reports nothing: what was known stays.
    repair.store(s.host, BROKEN)
    assert repair.store(s.host, None) is False and s.host.package_manager_needs_repair


def test_an_unknown_manager_is_never_flagged(session):
    s = _setup(session)
    repair.store(s.host, {"manager": "rm -rf", "needs_repair": True, "reason": "x"})
    assert not s.host.package_manager_needs_repair


@pytest.mark.asyncio
async def test_repair_is_queued_only_where_it_can_run(session, sent):
    s = _setup(session)
    other = _host(session, fqdn="other.lab")
    dnf = _host(session, fqdn="dnf.lab")
    for host in (s.host, other, dnf):
        _able(host)
    repair.store(s.host, BROKEN)
    repair.store(
        dnf,
        {"manager": "dnf", "needs_repair": True, "repairable": False, "reason": "x"},
    )
    session.commit()
    body = api.RepairBody(host_ids=[str(s.host.id), str(other.id), str(dnf.id), "nope"])
    answer = await api.repair_package_managers(body, session, PATCHER)
    assert answer["started"] == 1
    reasons = {row["fqdn"]: row["reason"] for row in answer["skipped"]}
    assert reasons == {
        "other.lab": "not_needed",
        "dnf.lab": "not_repairable",
        None: "no_host",
    }
    assert sent[-1][1] == "repair_package_manager"


@pytest.mark.asyncio
async def test_repair_needs_the_apply_updates_role(session, sent):
    s = _setup(session)
    body = api.RepairBody(host_ids=[str(s.host.id)])
    assert await _status(api.repair_package_managers(body, session, NOBODY)) == 403


def test_an_older_agent_is_told_to_upgrade(session):
    s = _setup(session)
    repair.store(s.host, BROKEN)
    s.host.agent_capabilities = json.dumps({"capabilities": []})
    assert repair.blocker(s.host) == repair.NOT_SUPPORTED


def test_the_result_keeps_the_health_after_the_repair(session):
    s = _setup(session)
    repair.store(s.host, BROKEN)
    message = {"result": {"success": True, "health": {"manager": "dpkg", "needs_repair": False,
                                                      "repairable": True}}}  # fmt: skip
    assert repair.record_result(session, s.host.id, message)
    assert not s.host.package_manager_needs_repair


def test_the_columns_come_and_go_idempotently():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        columns = _columns(db_path, "host")
        assert {"package_manager_needs_repair", "package_manager_repair_reason",
                "package_manager_repairable", "package_manager_name",
                "package_manager_checked_at"} <= set(columns)  # fmt: skip
        _alembic(["stamp", "q87tokennext"], db_path)
        _alembic(["upgrade", "head"], db_path)
        _alembic(["downgrade", "q87tokennext"], db_path)
        assert "package_manager_needs_repair" not in _columns(db_path, "host")
        _alembic(["upgrade", "head"], db_path)
    finally:
        os.unlink(db_path)


def test_the_update_scan_carries_the_health_to_the_host(session):
    s = _setup(session)
    repair.store_for_host(session, s.host.id, BROKEN)
    session.refresh(s.host)
    assert s.host.package_manager_needs_repair
    repair.store_for_host(session, s.host.id, None)  # an older agent: unchanged
    assert s.host.package_manager_needs_repair
