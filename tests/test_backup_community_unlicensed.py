# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Community backs up and restores with no Professional+ engine at all, and
every Pro+ backup surface refuses with 402 rather than failing or quietly
succeeding (ROADMAP 24.11 edition audit, 2026-11-03)."""

import json

import pytest
from fastapi import HTTPException

from backend.api import backups as api
from backend.api import backups_browse as browse
from backend.api import backups_drift as drift_api
from backend.api import backups_retention as retention
from backend.api import backups_breakglass as breakglass_api
from backend.api import backups_tag_policies as tag_api
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_breakglass as breakglass
from backend.services import backup_key_release as key_release
from backend.services import backup_results as results
from backend.services import backup_signing
from backend.services.backup_escrow import BREAK_GLASS_AUDIT
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _result,
    _setup,
    sent,
)
from tests.test_backups_api import MANAGER, RESTORER


@pytest.fixture(autouse=True)
def no_engines(monkeypatch):
    """Not one Pro+ engine loaded: backup, alerting, reporting, advisor..."""
    monkeypatch.setattr(module_loader, "get_module", lambda _code: None)


def _actions(sent_calls):
    return [p.get("action") for _h, _c, p in sent_calls if p.get("action")]


async def _code(coro):
    with pytest.raises(HTTPException) as refused:
        await coro
    return refused.value.status_code


@pytest.mark.asyncio
async def test_community_backs_up_and_restores_with_no_engine(session, sent):
    s = _setup(session)
    s.policy.host_abilities = json.dumps(["list", "status"])
    session.commit()
    host = str(s.host.id)

    # Back up now -> the capture result -> the storage chain (prune, du).
    run = await api.backup_now(host, api.RunBody(action="capture"), session, MANAGER)
    capture = session.query(models.BackupRun).filter_by(id=run["id"]).one()
    results.record_result(session, s.host.id, _result(capture, snapshot="s1"))
    assert capture.status == "ok"
    prune = session.query(models.BackupRun).filter_by(action="prune").one()
    results.record_result(session, s.nas.id, _result(prune, pruned=[]))
    assert _actions(sent)[:3] == ["capture", "prune", "du"]

    # Restore: the preview, then the real run (unsigned, acknowledged).
    body = {"snapshot": "s1", "include": ["/etc/hostname"]}
    preview = await api.backup_restore(host, api.RestoreBody(**body), session, RESTORER)
    real = await api.backup_restore(
        host,
        api.RestoreBody(**body, dry_run=False, acknowledge_unsigned=True),
        session,
        RESTORER,
    )
    assert preview["status"] == real["status"] == "queued"
    assert not json.loads(
        session.query(models.BackupRun).filter_by(id=real["id"]).one().parameters
    ).get("needs_key")

    # Browse a snapshot and ask what changed since it.
    listing = await browse.browse_snapshot(
        host, browse.BrowseBody(snapshot="s1"), session, RESTORER
    )
    changes = await browse.backup_changes(host, None, session, MANAGER)
    assert listing["action"] == jobs.LIST and changes["status"] == "queued"


@pytest.mark.asyncio
async def test_every_pro_plus_backup_surface_is_402_without_the_engine(session):
    s = _setup(session)
    session.commit()
    host = str(s.host.id)
    # Grandfather-father-son retention and its preview, scheduled
    # verification, package restore, the drift timeline and tag policies.
    assert await _code(retention.retention_preview(host, 3, 7, db=session)) == 402
    gfs = api.PolicyBody(keep_last=7, keep_daily=14)
    assert await _code(api.put_policy(host, gfs, session, MANAGER)) == 402
    verify = api.PolicyBody(keep_last=7, verify_interval_days=30)
    assert await _code(api.put_policy(host, verify, session, MANAGER)) == 402
    packages = api.RestoreBody(
        snapshot="s1", include=["/etc"], dry_run=True, in_place=True, packages=True
    )
    session.add(
        models.BackupSnapshot(
            policy_id=s.policy.id, host_id=s.host.id, name="s1",
            seen_at=s.policy.created_at,
        )
    )  # fmt: skip
    session.commit()
    assert await _code(api.backup_restore(host, packages, session, RESTORER)) == 402
    assert (
        await _code(drift_api.drift_timeline(host, db=session, current_user=RESTORER))
        == 402
    )
    assert (
        await _code(tag_api.list_tag_policies(db=session, current_user=MANAGER)) == 402
    )


def test_settings_pro_plus_wrote_keep_working_after_a_lapse(session):
    """A lapsed license never weakens what was chosen: GFS counts are still
    sent to the storage-side prune, and an encrypted policy's hosts still get
    the public key, so captures stay encrypted."""
    s = _setup(session)
    s.policy.keep_daily, s.policy.keep_weekly = 7, 4
    s.policy.encrypt_public_key = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n-----END PGP PUBLIC KEY BLOCK-----\n"
    )
    s.policy.encrypt_fingerprint = "A" * 40
    s.policy.encrypt_key_ref = "secret/data/secrets/backup_key/t/1"
    s.policy.repository_dir = jobs.repo_dir(s.host) + "-enc"
    s.policy.encrypted_at = s.policy.created_at
    session.commit()
    storage = jobs.storage_configuration(s.policy, s.target, s.host)
    assert storage["jobs"]["prune"]["keep_daily"] == 7
    assert storage["jobs"]["prune"]["keep_weekly"] == 4
    host_side = jobs.host_configuration(s.policy, s.target, s.host, s.nas)
    assert host_side["encrypt_key"].startswith("-----BEGIN PGP PUBLIC KEY BLOCK")


def _encrypted_lapsed(session):
    """A policy Pro+ encrypted, now with no engine loaded."""
    s = _setup(session)
    s.policy.encrypt_public_key = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n-----END PGP PUBLIC KEY BLOCK-----\n"
    )
    s.policy.encrypt_fingerprint = "A" * 40
    s.policy.encrypt_key_ref = "secret/data/secrets/backup_key/t/1"
    s.policy.repository_dir = jobs.repo_dir(s.host) + "-enc"
    s.policy.encrypted_at = s.policy.created_at
    s.policy.host_abilities = json.dumps(["decrypt", "list", "status"])
    session.add(
        models.BackupSnapshot(
            policy_id=s.policy.id, host_id=s.host.id, name="e1",
            seen_at=s.policy.created_at, repository_dir=s.policy.repository_dir,
        )
    )  # fmt: skip
    session.commit()
    return s


def _needs_key(session, run_id):
    run = session.query(models.BackupRun).filter_by(id=run_id).one()
    return json.loads(run.parameters).get("needs_key"), run


@pytest.mark.asyncio
async def test_a_lapse_never_locks_anyone_out_of_their_encrypted_backups(
    session, sent, monkeypatch
):
    """ "Please don't hold someone's safety hostage" (Bryan, 2026-11-03): with
    no engine at all, an encrypted snapshot's restore, browse and what-changed
    all ask for the key, and the key is released from OpenBAO for the run."""
    s = _encrypted_lapsed(session)
    host = str(s.host.id)
    body = {"snapshot": "e1", "include": ["/etc/hostname"]}
    preview = await api.backup_restore(host, api.RestoreBody(**body), session, RESTORER)
    real = await api.backup_restore(
        host,
        api.RestoreBody(**body, dry_run=False, acknowledge_unsigned=True),
        session,
        RESTORER,
    )
    listing = await browse.browse_snapshot(
        host, browse.BrowseBody(snapshot="e1"), session, RESTORER
    )
    changes = await browse.backup_changes(host, None, session, MANAGER)
    for out in (preview, real, listing, changes):
        needs_key, _run = _needs_key(session, out["id"])
        assert needs_key is True
    secret = "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsec\n"
    monkeypatch.setattr(
        key_release.backup_keys_read, "secret_keys",
        lambda policy, db=None, vault=None: [secret],
    )  # fmt: skip
    assert key_release.release(session, host, real["id"]) == [secret]


def test_a_lapse_keeps_backups_encrypted_and_stops_only_signing(session):
    """After a lapse the hosts still get the public key (captures stay
    encrypted, never plaintext into the encrypted repository) and the signer's
    public key (restores keep checking signatures), while signing new
    snapshots stops quietly instead of failing a sign job every night."""
    s = _encrypted_lapsed(session)
    s.target.sign_public_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\ns\n"
    s.target.sign_key_ref = "secret/data/secrets/backup_sign/t/1"
    s.policy.storage_abilities = json.dumps(["sign"])
    session.commit()
    host_side = jobs.host_configuration(s.policy, s.target, s.host, s.nas)
    assert host_side["encrypt_key"].startswith("-----BEGIN PGP PUBLIC KEY BLOCK")
    assert host_side["target"]["repo_dir"].endswith("-enc")
    assert host_side["trusted_key"].startswith("-----BEGIN PGP PUBLIC KEY BLOCK")
    assert backup_signing.wanted(session, s.policy) is False


@pytest.mark.asyncio
async def test_the_break_glass_export_works_after_a_lapse(session, monkeypatch):
    """Getting your keys out needs no license: the same sealed export, the
    same per-host audit the escrow status reads."""
    s = _encrypted_lapsed(session)
    monkeypatch.setattr(
        breakglass, "inspect_recipient", lambda key: ("F" * 40, "Operator <o@x>")
    )
    monkeypatch.setattr(
        breakglass, "gather_export",
        lambda db, pairs, target: [{
            "host": pairs[0][0].fqdn, "host_id": str(pairs[0][0].id),
            "policy_id": str(pairs[0][1].id), "repository": "r",
            "previous_repository": None, "storage_repository": None,
            "keys": [{"fingerprint": "A" * 40, "subkey_id": None,
                      "created_at": None, "replaced_at": None,
                      "secret": "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsec\n"}],
        }],
    )  # fmt: skip
    monkeypatch.setattr(
        breakglass,
        "seal_bundle",
        lambda bundle, public, fingerprint: "-----BEGIN PGP MESSAGE-----\nx\n",
    )
    info = await breakglass_api.break_glass_info(db=session)
    assert info["available"] is True and info["encrypted_hosts"] == 1
    body = breakglass_api.BreakGlassBody(
        recipient_key="-----BEGIN PGP PUBLIC KEY BLOCK-----\nop\n",
        reason="annual DR escrow after the lapse",
    )
    response = await breakglass_api.break_glass_export(body, session, RESTORER)
    assert response.body.startswith(b"-----BEGIN PGP MESSAGE-----")
    assert "sysmanage-backup-keys-" in response.headers["content-disposition"]
    audited = (
        session.query(models.AuditLog)
        .filter(models.AuditLog.description == BREAK_GLASS_AUDIT)
        .all()
    )
    assert [a.entity_name for a in audited] == [s.host.fqdn]
    with pytest.raises(HTTPException) as refused:  # Manage Backups alone
        await breakglass_api.break_glass_export(body, session, MANAGER)
    assert refused.value.status_code == 403
