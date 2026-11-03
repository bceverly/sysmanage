# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

""" "Use the tag policy" (Pro+ 24.6, 2026-11-03): a host on its own policy is
handed back to the tag policy that covers it WITHOUT removing its policy --
the only way back before was deleting the policy, which orphans an encrypted
host's keys and repository.  Only the settings a tag policy controls change."""

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import backups as backups_api
from backend.api import backups_tag_policies as api
from backend.persistence import models
from backend.services import backup_tag_policies as tag_policies
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _host,
    _setup,
    sent,
)
from tests.services.test_backup_tag_policies import _policy, _tag, _tag_host, _template
from tests.test_backups_api import MANAGER

PUBLIC = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n-----END PGP PUBLIC KEY BLOCK-----\n"


@pytest.fixture(autouse=True)
def backup_engine_loaded():
    with patch.object(tag_policies, "engine_loaded", return_value=True):
        yield


def _encrypted_own(session):
    """An acknowledged, encrypted host on its OWN policy, covered by a tag."""
    s = _setup(session)
    policy = s.policy
    policy.keep_last = 30
    policy.window_start_hour = 2
    policy.previous_repository_dir = "web01-1f3a9c2e"
    policy.repository_dir = "web01-1f3a9c2e-enc"
    policy.encrypt_public_key = PUBLIC
    policy.encrypt_fingerprint = "A" * 40
    policy.encrypt_key_ref = "secret/data/secrets/backup_key/tenant/1"
    policy.host_acked_version = policy.config_version
    session.add(models.BackupPolicyKey(
        id=uuid.uuid4(), policy_id=policy.id, fingerprint="A" * 40,
        key_ref="secret/data/secrets/backup_key/tenant/1",
        created_at=backups_api.jobs.now(),
    ))  # fmt: skip
    tag = _tag(session, "servers")
    _tag_host(session, s.host, tag)
    row = _template(session, "Servers nightly", tag, priority=10, keep_last=7,
                    keep_daily=14, window_start_hour=5)  # fmt: skip
    session.commit()
    return s, row


def _keys(session, policy):
    return (
        session.query(models.BackupPolicyKey)
        .filter(models.BackupPolicyKey.policy_id == policy.id)
        .count()
    )


@pytest.mark.asyncio
async def test_an_encrypted_host_keeps_its_keys_and_repositories(session, sent):
    s, row = _encrypted_own(session)
    policy_id, version = s.policy.id, s.policy.config_version
    preview = await api.preview_use_tag_policy(str(s.host.id), session, MANAGER)
    assert preview["tag_policy"]["name"] == "Servers nightly"
    replaced = {c["key"] for c in preview["changes"]}
    assert {"keep_last", "keep_daily", "window_start_hour"} <= replaced

    result = await api.use_tag_policy(str(s.host.id), session, MANAGER)
    policy = _policy(session, s.host)
    assert policy.id == policy_id  # the same row, never deleted
    assert policy.tag_policy_id == row.id
    assert (policy.keep_last, policy.keep_daily, policy.window_start_hour) == (7, 14, 5)
    assert policy.repository_dir == "web01-1f3a9c2e-enc"
    assert policy.previous_repository_dir == "web01-1f3a9c2e"
    assert policy.encrypt_fingerprint == "A" * 40
    assert policy.encrypt_key_ref == "secret/data/secrets/backup_key/tenant/1"
    assert _keys(session, policy) == 1
    assert policy.config_version == version + 1  # the hosts get new job files
    assert result["source"]["kind"] == "tag"
    audit = (
        session.query(models.AuditLog)
        .filter(models.AuditLog.description == "Backup policy handed to its tag policy")
        .one()
    )
    assert audit.entity_name == s.host.fqdn


@pytest.mark.asyncio
async def test_nothing_to_switch_to_is_refused(session, sent):
    s = _setup(session)  # its own policy, no tag covers it
    with pytest.raises(HTTPException) as refused:
        await api.use_tag_policy(str(s.host.id), session, MANAGER)
    assert refused.value.status_code == 409
    assert "nothing to switch to" in refused.value.detail
    assert _policy(session, s.host).tag_policy_id is None


@pytest.mark.asyncio
async def test_a_host_already_on_its_tag_policy_is_refused(session, sent):
    s, _row = _encrypted_own(session)
    await api.use_tag_policy(str(s.host.id), session, MANAGER)
    with pytest.raises(HTTPException) as refused:
        await api.use_tag_policy(str(s.host.id), session, MANAGER)
    assert refused.value.status_code == 409


@pytest.mark.asyncio
async def test_unlicensed_is_402(session, sent):
    s, _row = _encrypted_own(session)
    with patch.object(tag_policies, "engine_loaded", return_value=False):
        for call in (api.use_tag_policy, api.preview_use_tag_policy):
            with pytest.raises(HTTPException) as refused:
                await call(str(s.host.id), session, MANAGER)
            assert refused.value.status_code == 402
    assert _policy(session, s.host).tag_policy_id is None


@pytest.mark.asyncio
async def test_own_then_tag_then_configure_then_own_again(session, sent):
    s, row = _encrypted_own(session)
    policy = _policy(session, s.host)
    source = tag_policies.source_of(session, policy)
    assert source["kind"] == "own" and source["tag_policy_available"]["id"] == str(
        row.id
    )
    await api.use_tag_policy(str(s.host.id), session, MANAGER)
    assert tag_policies.source_of(session, policy)["kind"] == "tag"
    tag_policies.resolve(session)  # the next pass keeps it on the tag policy
    assert _policy(session, s.host).tag_policy_id == row.id
    body = backups_api.PolicyBody(**tag_policies.policy_settings(policy))
    await backups_api.put_policy(str(s.host.id), body, session, MANAGER)
    policy = _policy(session, s.host)
    assert policy.tag_policy_id is None
    assert policy.encrypt_fingerprint == "A" * 40 and _keys(session, policy) == 1
    assert tag_policies.source_of(session, policy)["kind"] == "own"
