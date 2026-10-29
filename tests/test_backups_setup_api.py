# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Set up backups for many hosts at once (2026-10-29): each equipped host
without a policy gets the default one; the rest come back with why."""

import json
from unittest.mock import patch

import pytest

from backend.api import backups_retention as retention
from backend.api import backups_setup as setup
from backend.persistence import models
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _host,
    _setup,
    sent,
)
from tests.test_backups_api import MANAGER, NOBODY, _status


def _policy(session, host):
    return (
        session.query(models.BackupPolicy)
        .filter(models.BackupPolicy.host_id == host.id)
        .first()
    )


@pytest.mark.asyncio
async def test_equipped_hosts_without_a_policy_get_the_defaults(session, sent):
    s = _setup(session)  # s.host already has a policy
    fresh = _host(session, fqdn="fresh.lab")
    bare = _host(session, fqdn="bare.lab", caps=json.dumps({"capabilities": []}))
    body = setup.BulkSetupBody(host_ids=[str(fresh.id), str(s.host.id), str(bare.id),
                                         "00000000-0000-4000-8000-000000000000"])  # fmt: skip
    with patch.object(retention, "_engine", return_value=object()):
        answer = await setup.bulk_backup_setup(body, session, MANAGER)
    assert answer["created"] == 1
    reasons = {s_["fqdn"]: s_["reason"] for s_ in answer["skipped"]}
    assert reasons == {
        s.host.fqdn: "has_policy",
        "bare.lab": "not_equipped",
        None: "no_host",
    }
    policy = _policy(session, fresh)
    assert (policy.keep_last, policy.keep_daily, policy.keep_weekly,
            policy.keep_monthly, policy.keep_yearly) == (7, 14, 8, 12, 3)  # fmt: skip
    assert policy.enabled and policy.interval_hours == 24
    assert policy.window_start_hour == setup.DEFAULT_START_HOUR
    assert policy.quiesce is False and policy.config_version == 1


@pytest.mark.asyncio
async def test_no_years_where_the_storage_host_cannot_keep_them(session, sent):
    s = _setup(session)
    s.policy.storage_abilities = "[]"  # its restate reported, without years
    session.flush()
    fresh = _host(session, fqdn="fresh.lab")
    with patch.object(retention, "_engine", return_value=object()):
        await setup.bulk_backup_setup(
            setup.BulkSetupBody(host_ids=[str(fresh.id)]), session, MANAGER
        )
    policy = _policy(session, fresh)
    assert policy.keep_monthly == 12 and not policy.keep_yearly


@pytest.mark.asyncio
async def test_without_the_engine_a_month_of_dailies(session, sent):
    _setup(session)
    fresh = _host(session, fqdn="fresh.lab")
    with patch.object(retention, "_engine", return_value=None):
        await setup.bulk_backup_setup(
            setup.BulkSetupBody(host_ids=[str(fresh.id)]), session, MANAGER
        )
    policy = _policy(session, fresh)
    assert policy.keep_last == 30 and not policy.keep_daily


@pytest.mark.asyncio
async def test_needs_the_role_and_a_target(session, sent):
    fresh = _host(session, fqdn="fresh.lab")
    body = setup.BulkSetupBody(host_ids=[str(fresh.id)])
    assert await _status(setup.bulk_backup_setup(body, session, NOBODY)) == 403
    assert await _status(setup.bulk_backup_setup(body, session, MANAGER)) == 409
