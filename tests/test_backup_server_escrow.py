# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The SysManage server's own backup, encrypted to the escrow key (ROADMAP
25.9, Pro+).  Never keyed from its own OpenBAO, never unencrypted on Pro+;
SysManage never holds its key, so it neither restores nor verifies it -- the
runbook does, by hand -- and the break-glass export has nothing of it."""

# pylint: disable=redefined-outer-name,unused-argument,unused-import

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import backups as api
from backend.api import backups_escrow as escrow_api
from backend.api import backups_server as server_api
from backend.persistence import models
from backend.services import backup_breakglass, backup_escrow
from backend.services import backup_jobs as jobs
from backend.services import backup_server, backup_verify
from tests.services.test_backup_results import _host, _setup
from tests.test_backups_api import (
    MANAGER,
    _status,
    sent,
)  # noqa: F401  # pylint: disable=unused-import

PUBLIC = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n-----END PGP PUBLIC KEY BLOCK-----\n"


class _Engine:
    """backup_engine's escrow_encryption, as far as the server sees it."""

    class EncryptionRefused(Exception):
        pass

    def __init__(self):
        self.calls = []

    def escrow_encryption(self, db, policy, host, target, has_snapshots):
        self.calls.append((policy.host_id, target.escrow_fingerprint, has_snapshots))
        policy.encrypt_public_key = target.escrow_public_key
        policy.encrypt_fingerprint = target.escrow_fingerprint
        policy.encrypt_key_ref = None
        return {"encrypted": True, "fingerprint": target.escrow_fingerprint}


@pytest.fixture
def proplus():
    found = _Engine()
    with patch.object(backup_escrow, "backup_engine", return_value=found):
        yield found


def _server(session, escrow=True):
    s = _setup(session)
    s.server = _host(session, fqdn="sysmanage.example.com")
    if escrow:
        s.target.escrow_public_key = PUBLIC
        s.target.escrow_fingerprint = "E" * 40
    session.flush()
    return s


def _body(host):
    return server_api.ServerPolicyBody(host_id=str(host.id))


@pytest.mark.asyncio
async def test_pro_without_an_escrow_key_refuses_the_server_policy(
    session, proplus, sent
):
    s = _server(session, escrow=False)
    assert (
        await _status(server_api.put_server_policy(_body(s.server), session, MANAGER))
        == 409
    )
    assert backup_server.marked(session) is None and proplus.calls == []


@pytest.mark.asyncio
async def test_pro_encrypts_the_server_policy_to_the_escrow_key(session, proplus, sent):
    s = _server(session)
    await server_api.put_server_policy(_body(s.server), session, MANAGER)
    assert proplus.calls == [(s.server.id, "E" * 40, False)]
    policy = backup_server.marked(session)
    assert jobs.escrow_keyed(policy)
    found = await server_api.server_backup(None, session)
    assert found["encryption"] == {"available": True, "escrow_fingerprint": "E" * 40,
                                   "encrypted": True}  # fmt: skip


@pytest.mark.asyncio
async def test_community_backs_the_server_up_unencrypted(session, sent):
    s = _server(session, escrow=False)
    await server_api.put_server_policy(_body(s.server), session, MANAGER)
    assert not jobs.encrypted(backup_server.marked(session))
    assert (await server_api.server_backup(None, session))["encryption"] == {
        "available": False
    }


@pytest.mark.asyncio
async def test_a_new_escrow_key_moves_the_server_backup_to_it(session, proplus, sent):
    s = _server(session)
    await server_api.put_server_policy(_body(s.server), session, MANAGER)
    with patch.object(backup_breakglass, "inspect_recipient",
                      lambda key: ("F" * 40, "Escrow <e@example.lab>")):  # fmt: skip
        await escrow_api.save_escrow_key(escrow_api.EscrowKeyBody(public_key=PUBLIC),
                                         session, MANAGER)  # fmt: skip
    assert proplus.calls[-1] == (s.server.id, "F" * 40, False)
    audit = session.query(models.AuditLog).all()
    assert any("encrypted to the escrow key" in a.description for a in audit)


def _escrow_keyed(session):
    s = _setup(session)
    s.policy.server_preset = True
    s.policy.encrypt_public_key = PUBLIC
    s.policy.encrypt_fingerprint = "E" * 40
    session.flush()
    return s


def test_sysmanage_never_restores_or_verifies_what_only_the_operator_can_read(session):
    s = _escrow_keyed(session)
    with pytest.raises(HTTPException) as refused:
        api.key_needed(jobs.CURRENT, s.policy)
    assert refused.value.status_code == 409 and "by hand" in refused.value.detail
    s.policy.verify_interval_days = 30
    s.policy.host_abilities = '["verify", "decrypt"]'
    with patch.object(backup_verify, "due", return_value=True), \
            patch.object(jobs, "queue_verify") as queued:  # fmt: skip
        assert (
            backup_verify.maybe_verify(session, s.policy, s.host, jobs.now()) is False
        )
    queued.assert_not_called()


def test_the_break_glass_export_has_nothing_of_it_and_is_not_stale_for_it(
    session, proplus
):
    _escrow_keyed(session)
    assert backup_breakglass.encrypted_pairs(session) == []
    status = backup_escrow.status(session)
    assert status["encrypted_hosts"] == 0 and status["stale_hosts"] == []


def test_an_earlier_openbao_key_of_it_is_still_exported(session, proplus):
    s = _escrow_keyed(session)
    session.add(models.BackupPolicyKey(id=uuid.uuid4(), policy_id=s.policy.id,
                                       fingerprint="A" * 40, key_ref="sysmanage/k/a",
                                       created_at=jobs.now()))  # fmt: skip
    session.flush()
    assert [p.id for _h, p in backup_breakglass.encrypted_pairs(session)] == [
        s.policy.id
    ]
