# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backup policies by tag (Pro+ 24.6): a tag policy's settings land on each
tagged host's own policy row; the lowest priority wins; a host's own policy
(Configure) beats them all; untagging removes what the tag gave; a paused
tag policy keeps it; nothing happens without the engine."""

import json
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import backups as backups_api
from backend.api import backups_tag_policies as api
from backend.persistence import models
from backend.services import backup_tag_policies as tag_policies
from backend.services import backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _host,
    _setup,
    sent,
)
from tests.test_backups_api import MANAGER

STAMP = datetime(2026, 11, 3, 5, 0)


@pytest.fixture(autouse=True)
def backup_engine_loaded():
    with patch.object(tag_policies, "engine_loaded", return_value=True):
        yield


def _tag(session, name):
    tag = models.Tag(id=uuid.uuid4(), name=name, created_at=STAMP, updated_at=STAMP)
    session.add(tag)
    session.commit()
    return tag


def _tag_host(session, host, tag):
    session.add(models.HostTag(id=uuid.uuid4(), host_id=host.id, tag_id=tag.id,
                               created_at=STAMP))  # fmt: skip
    session.commit()


def _template(session, name, tag, priority=100, enabled=True, **settings):
    base = backups_api.PolicyBody(**settings).model_dump()
    row = models.BackupTagPolicy(
        id=uuid.uuid4(), name=name, tag_id=tag.id, priority=priority,
        enabled=enabled, settings=json.dumps(base), created_at=STAMP,
        updated_at=STAMP,
    )  # fmt: skip
    session.add(row)
    session.commit()
    return row


def _policy(session, host):
    return (
        session.query(models.BackupPolicy)
        .filter(models.BackupPolicy.host_id == host.id)
        .first()
    )


def test_a_tagged_host_gets_the_tag_policys_settings(session, sent):
    s = _setup(session)
    new = _host(session, fqdn="db01.lab")
    servers = _tag(session, "servers")
    _tag_host(session, new, servers)
    row = _template(session, "Servers nightly", servers, priority=10, keep_last=7,
                    keep_daily=14, keep_weekly=8, window_start_hour=5)  # fmt: skip
    outcome = tag_policies.resolve(session)
    policy = _policy(session, new)
    assert [a["fqdn"] for a in outcome.applied] == ["db01.lab"]
    assert (policy.keep_last, policy.keep_daily, policy.keep_weekly) == (7, 14, 8)
    assert policy.window_start_hour == 5 and policy.target_id == s.target.id
    assert policy.tag_policy_id == row.id
    assert tag_policies.source_of(session, policy) == {
        "kind": "tag", "id": str(row.id), "name": "Servers nightly", "priority": 10,
    }  # fmt: skip
    assert views.host_status(session, new)["policy_source"]["name"] == "Servers nightly"


def test_the_lowest_priority_wins_and_a_change_moves_the_host(session, sent):
    _setup(session)
    host = _host(session, fqdn="app01.lab")
    web, prod = _tag(session, "web"), _tag(session, "prod")
    _tag_host(session, host, web)
    _tag_host(session, host, prod)
    _template(session, "Web", web, priority=50, keep_last=5)
    prod_row = _template(session, "Prod", prod, priority=20, keep_last=60)
    tag_policies.resolve(session)
    policy = _policy(session, host)
    assert (policy.keep_last, policy.tag_policy_id) == (60, prod_row.id)
    prod_row.priority = 90
    session.commit()
    policy.host_acked_version = policy.config_version  # as if configured
    version = policy.config_version
    tag_policies.resolve(session)
    assert policy.keep_last == 5 and policy.config_version == version + 1


def test_a_hosts_own_policy_always_wins(session, sent):
    s = _setup(session)  # s.host has its own policy (tag_policy_id NULL)
    tag = _tag(session, "everything")
    _tag_host(session, s.host, tag)
    _template(session, "Everything", tag, priority=0, keep_last=3)
    outcome = tag_policies.resolve(session)
    assert outcome.applied == []
    assert s.policy.keep_last == 14 and s.policy.tag_policy_id is None
    source = tag_policies.source_of(session, s.policy)
    assert source["kind"] == "own"
    assert (
        source["tag_policy_available"]["name"] == "Everything"
    )  # offered, not applied


def test_an_unchanged_policy_is_not_re_sent(session, sent):
    _setup(session)
    host = _host(session, fqdn="cache01.lab")
    tag = _tag(session, "cache")
    _tag_host(session, host, tag)
    _template(session, "Cache", tag, keep_last=9)
    tag_policies.resolve(session)
    policy = _policy(session, host)
    policy.host_acked_version = policy.config_version
    version = policy.config_version
    second = tag_policies.resolve(session)
    assert second.applied == [] and second.unchanged == 1
    assert policy.config_version == version


def test_untagging_removes_what_the_tag_gave_but_a_paused_one_keeps_it(session, sent):
    _setup(session)
    kept, gone = _host(session, fqdn="a.lab"), _host(session, fqdn="b.lab")
    paused_tag, live_tag = _tag(session, "paused"), _tag(session, "live")
    _tag_host(session, kept, paused_tag)
    _tag_host(session, gone, live_tag)
    paused_row = _template(session, "Paused", paused_tag)
    _template(session, "Live", live_tag)
    tag_policies.resolve(session)
    paused_row.enabled = False
    session.query(models.HostTag).filter(models.HostTag.host_id == gone.id).delete()
    session.commit()
    outcome = tag_policies.resolve(session)
    assert [r["fqdn"] for r in outcome.removed] == ["b.lab"]
    assert _policy(session, gone) is None
    assert _policy(session, kept) is not None  # paused, not torn down


def test_an_unequipped_host_is_skipped_with_the_reason(session, sent):
    _setup(session)
    bare = _host(session, fqdn="bare.lab", caps=None)
    tag = _tag(session, "bare")
    _tag_host(session, bare, tag)
    _template(session, "Bare", tag)
    outcome = tag_policies.resolve(session)
    assert outcome.skipped == [
        {"host_id": str(bare.id), "fqdn": "bare.lab", "reason": "not_equipped"}
    ]


def test_without_the_engine_nothing_is_applied(session, sent):
    _setup(session)
    host = _host(session, fqdn="x.lab")
    tag = _tag(session, "x")
    _tag_host(session, host, tag)
    _template(session, "X", tag)
    with patch.object(tag_policies, "engine_loaded", return_value=False):
        assert tag_policies.resolve(session).applied == []
    assert _policy(session, host) is None


def test_configure_makes_a_tag_given_policy_the_hosts_own(session, sent):
    _setup(session)
    host = _host(session, fqdn="own.lab")
    tag = _tag(session, "own")
    _tag_host(session, host, tag)
    _template(session, "Own", tag, keep_last=4)
    tag_policies.resolve(session)
    policy = _policy(session, host)
    assert policy.tag_policy_id is not None
    policy.tag_policy_id = None  # what put_policy does on save
    session.commit()
    tag_policies.resolve(session)
    source = tag_policies.source_of(session, policy)
    assert policy.tag_policy_id is None and source["kind"] == "own"
    # A tag policy still covers it, so the card offers "Use the tag policy".
    assert source["tag_policy_available"]["name"] == "Own"


def _body(tag, **over):
    fields = {"name": "Nightly", "tag_id": str(tag.id), "priority": 10,
              "settings": {"keep_last": 7, "keep_daily": 14}}  # fmt: skip
    fields.update(over)
    return api.TagPolicyBody(**fields)


@pytest.mark.asyncio
async def test_the_api_creates_applies_changes_and_removes(session, sent):
    _setup(session)
    host = _host(session, fqdn="api.lab")
    tag = _tag(session, "api")
    _tag_host(session, host, tag)
    made = await api.create_tag_policy(_body(tag), session, MANAGER)
    assert made["tag_policy"]["hosts_applied"] == 1
    assert [a["fqdn"] for a in made["applied"]["applied"]] == ["api.lab"]
    row_id = made["tag_policy"]["id"]
    changed = await api.update_tag_policy(
        row_id, _body(tag, settings={"keep_last": 21}), session, MANAGER
    )
    assert changed["tag_policy"]["settings"]["keep_last"] == 21
    assert _policy(session, host).keep_last == 21
    listed = await api.list_tag_policies(session, MANAGER)
    assert [p["name"] for p in listed["tag_policies"]] == ["Nightly"]
    gone = await api.delete_tag_policy(row_id, session, MANAGER)
    assert gone["deleted"] and _policy(session, host) is None
    audit = [r.description for r in session.query(models.AuditLog).all()]
    assert "Backup tag policy created" in audit and "Backup tag policy removed" in audit


@pytest.mark.asyncio
async def test_the_api_refuses_bad_input_and_runs_only_with_the_engine(session, sent):
    _setup(session)
    tag = _tag(session, "refuse")
    with pytest.raises(HTTPException) as bad:
        await api.create_tag_policy(_body(tag, priority=5000), session, MANAGER)
    assert bad.value.status_code == 422
    await api.create_tag_policy(_body(tag), session, MANAGER)
    with pytest.raises(HTTPException) as taken:
        await api.create_tag_policy(_body(tag), session, MANAGER)
    assert taken.value.status_code == 409
    with pytest.raises(HTTPException) as no_tag:
        await api.create_tag_policy(
            _body(tag, name="Other", tag_id=str(uuid.uuid4())), session, MANAGER
        )
    assert no_tag.value.status_code == 422
    with patch.object(tag_policies, "engine_loaded", return_value=False):
        with pytest.raises(HTTPException) as unlicensed:
            await api.list_tag_policies(session, MANAGER)
    assert unlicensed.value.status_code == 402
