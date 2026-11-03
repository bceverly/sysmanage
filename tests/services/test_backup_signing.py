# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Snapshot signing (Pro+ backup_engine, 24.6): the storage host signs each
snapshot between capture and protect with a key released for that run only;
a sign that fails or is refused never holds protect back; hosts get the
signer's public key; signed snapshots restore without an acknowledgment."""

import json
from datetime import datetime

import pytest

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_key_release as release
from backend.services import backup_results as results
from backend.services import backup_signing as signing
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _result,
    _setup,
    sent,
)

PUBLIC = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nsigner\n"
SECRET = "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsigner\n"
FPR = "B" * 40


def _signing(session, s, abilities=("keep_yearly", "sign")):
    s.target.sign_public_key = PUBLIC
    s.target.sign_fingerprint = FPR
    s.target.sign_key_ref = "secret/data/secrets/backup_key/tenant/x"
    s.target.signing_enabled_at = datetime(2026, 11, 2)
    s.policy.storage_abilities = json.dumps(list(abilities))
    s.policy.storage_protects = True
    session.commit()


def _capture(session, s, snapshot="20261102T120000Z"):
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_result(session, s.host.id, _result(run, snapshot=snapshot))
    return run


def _actions(sent):
    return [p.get("action") for _h, c, p in sent if c == "backup_run"]


def test_a_signed_target_signs_before_protect(session, sent):
    s = _setup(session)
    _signing(session, s)
    _capture(session, s)
    assert _actions(sent)[-1] == "sign"
    sign = session.query(models.BackupRun).filter_by(action="sign").one()
    params = json.loads(sign.parameters)
    assert str(sign.host_id) == str(s.nas.id)  # the STORAGE host signs
    assert params["needs_key"] is True and params["snapshot"] == "20261102T120000Z"
    assert "BEGIN PGP" not in sign.parameters  # never the key itself
    results.record_result(
        session,
        s.nas.id,
        _result(sign, signed="/srv/backups/restate/h::20261102T120000Z", signer=FPR),
    )
    snap = session.query(models.BackupSnapshot).one()
    assert snap.signed is True and snap.signer == FPR
    assert _actions(sent)[-1] == "protect"


def test_a_failed_or_refused_sign_never_holds_protect_back(session, sent):
    s = _setup(session)
    _signing(session, s)
    _capture(session, s)
    sign = session.query(models.BackupRun).filter_by(action="sign").one()
    results.record_result(session, s.nas.id, _result(sign, "failed"))
    assert session.query(models.BackupSnapshot).one().signed is False
    assert _actions(sent)[-1] == "protect"
    protect = session.query(models.BackupRun).filter_by(action="protect").one()
    results.record_result(session, s.nas.id, _result(protect))
    # An older agent refuses the action outright: still protect, and the
    # storage host's job files are not thrown away.
    _capture(session, s, "20261102T130000Z")
    sign2 = (
        session.query(models.BackupRun).filter_by(action="sign", status="queued").one()
    )
    results.record_command_result(session, {
        "command_id": sign2.command_id, "success": False, "reason": "not_configured",
        "error": "not configured"})  # fmt: skip
    assert _actions(sent)[-1] == "protect" and s.policy.storage_acked_version == 1


def test_no_signing_when_off_or_the_storage_restate_cannot(session, sent):
    s = _setup(session)
    s.policy.storage_protects = True
    session.commit()
    _capture(session, s)
    assert "sign" not in _actions(sent)
    _signing(session, s, abilities=("keep_yearly",))
    _capture(session, s, "20261102T130000Z")
    assert _actions(sent).count("sign") == 0


def test_hosts_get_only_the_public_key(session):
    s = _setup(session)
    _signing(session, s)
    host = jobs.host_configuration(s.policy, s.target, s.host, s.nas)
    assert host["trusted_key"] == PUBLIC
    storage = jobs.storage_configuration(s.policy, s.target, s.host)
    assert "trusted_key" not in storage and SECRET not in json.dumps(storage)


class _Engine:
    def __init__(self):
        self.asked = []

    def signing_secret_key(self, target):
        self.asked.append(target.id)
        return SECRET


@pytest.fixture
def loaded(monkeypatch):
    found = {"backup_engine": _Engine()}
    monkeypatch.setattr(release.module_loader, "get_module", found.get)
    return found


def test_the_signing_key_goes_to_the_storage_host_once(session, sent, loaded):
    s = _setup(session)
    _signing(session, s)
    _capture(session, s)
    sign = session.query(models.BackupRun).filter_by(action="sign").one()
    with pytest.raises(release.KeyRefused) as wrong:
        release.release(session, str(s.host.id), sign.id)  # the backed-up host
    assert wrong.value.status == 404
    assert release.release(session, str(s.nas.id), sign.id) == [SECRET]
    with pytest.raises(release.KeyRefused) as again:
        release.release(session, str(s.nas.id), sign.id)
    assert again.value.status == 409
    assert loaded["backup_engine"].asked == [s.target.id]


def test_no_signing_key_when_signing_is_off(session, sent, loaded):
    s = _setup(session)
    run = signing.queue_sign(session, s.policy, s.nas.id, "20261102T120000Z")
    session.commit()
    with pytest.raises(release.KeyRefused) as off:
        release.release(session, str(s.nas.id), run.id)
    assert off.value.status == 409


@pytest.mark.asyncio
async def test_a_signed_snapshot_restores_without_the_acknowledgment(session, sent):
    """Checked against the signer's key on the host instead (trusted_key):
    no allow_unverified is sent, so a bad signature is refused there."""
    import uuid  # pylint: disable=import-outside-toplevel

    from backend.api import backups as api  # pylint: disable=import-outside-toplevel
    from tests.test_backups_api import (
        RESTORER,
    )  # pylint: disable=import-outside-toplevel

    s = _setup(session)
    _signing(session, s)
    session.add(models.BackupSnapshot(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id,
        name="20261102T120000Z", signed=True, signer=FPR, seen_at=datetime(2026, 11, 2),
    ))  # fmt: skip
    session.commit()
    body = api.RestoreBody(snapshot="20261102T120000Z", include=["/etc/nginx"],
                           dry_run=False)  # fmt: skip
    await api.backup_restore(str(s.host.id), body, session, RESTORER)
    _host, command, params = sent[-1]
    assert command == "backup_restore" and params["allow_unverified"] is False
