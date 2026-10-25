# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Encrypted repositories in the OSS plumbing (Pro+ backup_engine, 24.6 S3).

The engine makes the key pair and points the policy at a new repository; the
OSS side then sends the public key and both repositories to the host, keeps
the old repository's snapshots, reads each snapshot from the repository that
holds it, refuses an encrypted one until restate can take the key for one
job (S4), and prepares the new repository's export once."""

import json
import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from backend.api import backups as api
from backend.api import backups_browse as browse
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _ack_storage,
    _result,
    _setup,
    sent,
)
from tests.test_backups_api import MANAGER, RESTORER

PUBLIC = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n-----END PGP PUBLIC KEY BLOCK-----\n"
WHEN = datetime(2026, 10, 25, 12, 0)


def _encrypt(session, s):
    """What backup_engine.enable_encryption leaves on the policy."""
    base = jobs.repo_dir(s.host)
    s.policy.previous_repository_dir = base
    s.policy.previous_nfs_path = "/restate/" + base
    s.policy.repository_dir = base + "-enc"
    s.policy.storage_nfs_path = None
    s.policy.encrypt_public_key = PUBLIC
    s.policy.encrypt_fingerprint = "A" * 40
    s.policy.encrypt_key_ref = "secret/data/secrets/backup_key/server/1"
    s.policy.encrypted_at = WHEN
    s.policy.config_version += 1
    session.commit()
    return base


def _snapshot(session, s, name, repository_dir=None):
    row = models.BackupSnapshot(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, name=name,
        signed=False, seen_at=WHEN, repository_dir=repository_dir,
    )  # fmt: skip
    session.add(row)
    session.commit()
    return row


def test_a_plain_policy_sends_no_key_and_no_previous_repository(session):
    s = _setup(session)
    host = jobs.host_configuration(s.policy, s.target, s.host, s.nas)
    assert "encrypt_key" not in host and "previous" not in host["target"]
    assert host["target"]["repo_dir"] == jobs.repo_dir(s.host)
    assert views.policy_dict(s.policy)["encryption"] is None


def test_an_encrypted_policy_sends_the_public_key_and_both_repositories(session):
    s = _setup(session)
    s.nas.ipv4 = "192.168.4.212"
    base = _encrypt(session, s)
    host = jobs.host_configuration(s.policy, s.target, s.host, s.nas)
    assert host["encrypt_key"] == PUBLIC  # never the secret key
    assert host["target"]["repo_dir"] == base + "-enc"
    assert host["target"]["previous"] == {
        "repo_dir": base, "nfs": {"server": "192.168.4.212", "path": "/restate/" + base}
    }  # fmt: skip
    storage = jobs.storage_configuration(s.policy, s.target, s.host)
    assert storage["target"]["repo_dir"] == base + "-enc"
    assert "encrypt_key" not in storage  # the storage host stays keyless
    shown = views.policy_dict(s.policy)["encryption"]
    assert shown == {"fingerprint": "A" * 40, "since": "2026-10-25T12:00:00",
                     "previous_repository": base}  # fmt: skip
    assert "secret/" not in json.dumps(views.policy_dict(s.policy))


def test_the_new_repositorys_listing_keeps_the_old_snapshots(session):
    s = _setup(session)
    _snapshot(session, s, "20261020T010000Z")  # the plain repository's
    _encrypt(session, s)
    run = jobs.queue_run(session, s.policy, s.host.id, "snapshots")
    results.record_result(
        session, s.host.id,
        _result(run, "ok", snapshots=[{"name": "20261025T130000Z"}]),
    )  # fmt: skip
    rows = {r.name: r for r in session.query(models.BackupSnapshot).all()}
    assert rows["20261020T010000Z"].gone_at is None  # still restorable
    assert rows["20261025T130000Z"].repository_dir == s.policy.repository_dir


class _Engine:
    """backup_engine as the OSS side sees it (loaded)."""


@pytest.fixture
def loaded_engine(monkeypatch):
    loaded = {"backup_engine": _Engine()}
    monkeypatch.setattr(api.module_loader, "get_module", loaded.get)
    return loaded


def _keyed(session, s, abilities=("list", "status", "decrypt")):
    _snapshot(session, s, "20261020T010000Z")
    _encrypt(session, s)
    _snapshot(session, s, "20261025T130000Z", s.policy.repository_dir)
    s.policy.host_abilities = json.dumps(list(abilities))
    session.commit()
    return str(s.host.id)


def _restore(name):
    return api.RestoreBody(
        snapshot=name, include=["/etc/hosts"], acknowledge_unsigned=True
    )


@pytest.mark.asyncio
async def test_a_restore_reads_the_repository_that_holds_the_snapshot(
    session, sent, loaded_engine
):
    s = _setup(session)
    host = _keyed(session, s)
    await api.backup_restore(host, _restore("20261020T010000Z"), session, RESTORER)
    assert sent[-1][2]["previous"] is True and "needs_key" not in sent[-1][2]
    await api.backup_restore(host, _restore("20261025T130000Z"), session, RESTORER)
    params = sent[-1][2]
    assert params["needs_key"] is True and "previous" not in params
    # The key itself never goes in the command (the queue) or the run row.
    stored = session.query(models.BackupRun).filter_by(action=jobs.RESTORE).all()
    assert all("PRIVATE KEY" not in (r.parameters or "") for r in stored)
    assert "PRIVATE KEY" not in json.dumps(params)


@pytest.mark.asyncio
async def test_without_the_engine_an_encrypted_snapshot_is_refused(session, sent):
    s = _setup(session)
    host = _keyed(session, s)
    with pytest.raises(HTTPException) as refused:
        await api.backup_restore(host, _restore("20261025T130000Z"), session, RESTORER)
    assert refused.value.status_code == 409 and "backup engine" in refused.value.detail


@pytest.mark.asyncio
async def test_a_restate_that_cannot_decrypt_is_refused(session, sent, loaded_engine):
    s = _setup(session)
    host = _keyed(session, s, abilities=("list", "status"))
    with pytest.raises(HTTPException) as refused:
        await api.backup_restore(host, _restore("20261025T130000Z"), session, RESTORER)
    assert (
        refused.value.status_code == 409 and "upgrade restate" in refused.value.detail
    )


@pytest.mark.asyncio
async def test_browsing_and_what_changed_ask_for_the_key(session, sent, loaded_engine):
    s = _setup(session)
    host = _keyed(session, s)
    await browse.browse_snapshot(
        host, browse.BrowseBody(snapshot="20261020T010000Z"), session, RESTORER
    )
    assert sent[-1][2]["previous"] is True and "needs_key" not in sent[-1][2]
    await browse.browse_snapshot(
        host, browse.BrowseBody(snapshot="20261025T130000Z"), session, RESTORER
    )
    assert sent[-1][2]["needs_key"] is True
    await browse.backup_changes(host, None, session, MANAGER)
    assert sent[-1][2]["action"] == jobs.STATUS and sent[-1][2]["needs_key"] is True


def test_the_new_repository_is_prepared_once_on_the_storage_acknowledgment(
    session, sent
):
    s = _setup(session)
    s.host.ipv4 = "192.168.4.196"
    _ack_storage(session, s)
    prepare = jobs.queue_run(session, s.policy, s.nas.id, jobs.PREPARE)
    results.record_result(session, s.nas.id, _result(prepare, "ok", kind="zfs"))
    _encrypt(session, s)
    sent.clear()
    _ack_storage(session, s)
    assert [p["action"] for _h, _c, p in sent if p.get("action")] == [jobs.PREPARE]
    queued = session.query(models.BackupRun).filter_by(
        action=jobs.PREPARE, status="queued"
    )
    run = queued.one()
    results.record_result(session, s.nas.id, _result(run, "ok", kind="zfs"))
    run.finished_at = datetime(2026, 10, 25, 12, 5)
    session.commit()
    sent.clear()
    _ack_storage(session, s)
    assert not [p for _h, _c, p in sent if p.get("action") == jobs.PREPARE]


def test_storage_never_prepared_is_not_prepared_for_encryption(session, sent):
    s = _setup(session)
    _encrypt(session, s)
    sent.clear()
    _ack_storage(session, s)
    assert not [p for _h, _c, p in sent if p.get("action") == jobs.PREPARE]


@pytest.mark.asyncio
async def test_an_encrypted_repository_is_never_repacked_on_the_storage_host(
    session, sent
):
    s = _setup(session)
    _encrypt(session, s)
    with pytest.raises(HTTPException) as refused:
        await api.backup_now(
            str(s.host.id), api.RunBody(action="repack"), session, MANAGER
        )
    assert refused.value.status_code == 409
    assert not [p for _h, _c, p in sent if p.get("action") == "repack"]
