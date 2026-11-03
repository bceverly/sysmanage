# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Break-glass escrow (ROADMAP 24.6, 2026-11-03): the fleet status the
Encryption panel, the Backups banner and the dashboard read; the remembered
escrow PUBLIC key; and the e-mail after a scheduled rotation."""

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api import backups_escrow as api
from backend.persistence import models
from backend.services import backup_escrow as escrow
from backend.services import backup_tick
from tests.services.test_backup_results import _setup

WHEN = datetime(2026, 11, 3, 12, 0)
PUBLIC = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n-----END PGP PUBLIC KEY BLOCK-----\n"
SECRET = (
    "-----BEGIN PGP PRIVATE KEY BLOCK-----\nk\n-----END PGP PRIVATE KEY BLOCK-----\n"
)


def _engine(**extra):
    module = SimpleNamespace(
        inspect_recipient=lambda key: ("F" * 40, "Escrow <escrow@example.lab>"), **extra
    )
    return patch.object(escrow, "backup_engine", return_value=module)


def _encrypt(session, s, at=WHEN):
    s.policy.encrypt_fingerprint = "A" * 40
    s.policy.encrypt_public_key = PUBLIC
    s.policy.encrypted_at = at
    session.flush()


def _export(session, host, when, recipient="F" * 40):
    session.add(
        models.AuditLog(
            id=uuid.uuid4(), timestamp=when, action_type="UPDATE", entity_type="host",
            entity_id=str(host.id), username="bryan@example.lab",
            description=escrow.BREAK_GLASS_AUDIT, result="SUCCESS",
            details={"recipient": recipient, "reason": "annual escrow"},
        )  # fmt: skip
    )
    session.flush()


def test_nothing_applies_in_community(session):
    s = _setup(session)
    _encrypt(session, s)
    with patch.object(escrow, "backup_engine", return_value=None):
        state = escrow.status(session)
    assert state["applies"] is False and state["stale"] is False


def test_nothing_applies_with_nothing_encrypted_and_signing_off(session):
    _setup(session)
    with _engine():
        state = escrow.status(session)
    assert state["applies"] is False and state["encrypted_hosts"] == 0


def test_an_encrypted_host_with_no_export_is_stale(session):
    s = _setup(session)
    _encrypt(session, s)
    with _engine():
        state = escrow.status(session)
    assert state["applies"] and state["stale"]
    assert state["last_export"] is None
    assert (state["encrypted_hosts"], state["covered_hosts"]) == (1, 0)
    assert state["stale_hosts"] == [s.host.fqdn]


def test_an_export_after_the_newest_key_covers_the_host(session):
    s = _setup(session)
    _encrypt(session, s)
    _export(session, s.host, WHEN + timedelta(minutes=5))
    with _engine():
        state = escrow.status(session)
    assert not state["stale"] and state["covered_hosts"] == 1
    assert state["last_export"]["by"] == "bryan@example.lab"
    assert state["last_export"]["recipient"] == "F" * 40
    assert state["last_export"]["at"].startswith("2026-11-03T12:05")


def test_a_rotation_after_the_export_makes_it_stale(session):
    s = _setup(session)
    _encrypt(session, s)
    _export(session, s.host, WHEN + timedelta(minutes=5))
    s.policy.encrypt_rotated_at = WHEN + timedelta(days=1)
    session.flush()
    with _engine():
        state = escrow.status(session)
    assert state["stale"] and state["stale_hosts"] == [s.host.fqdn]


def test_turning_signing_on_after_the_export_makes_it_stale(session):
    """The export also carries the signer's public key."""
    s = _setup(session)
    _encrypt(session, s)
    _export(session, s.host, WHEN + timedelta(minutes=5))
    s.target.signing_enabled_at = WHEN + timedelta(hours=1)
    session.flush()
    with _engine():
        state = escrow.status(session)
    assert state["signing_stale"] and state["stale"]
    assert state["stale_hosts"] == []


def test_signing_alone_applies(session):
    s = _setup(session)
    s.target.signing_enabled_at = WHEN
    session.flush()
    with _engine():
        state = escrow.status(session)
    assert state["applies"] and state["signing_on"] and state["stale"]


def test_the_shared_host_state_is_what_the_posture_check_reads(session):
    s = _setup(session)
    assert escrow.host_state(session, s.host, s.policy) is None  # plain
    _encrypt(session, s)
    assert escrow.host_state(session, s.host, s.policy) == "failing"
    _export(session, s.host, WHEN + timedelta(minutes=1))
    assert escrow.host_state(session, s.host, s.policy) == "ok"


def test_the_escrow_key_is_remembered_public_half_only(session):
    s = _setup(session)
    with _engine():
        saved = escrow.save_escrow_key(session, s.target, PUBLIC, "bryan@example.lab")
        state = escrow.status(session)
    assert saved["fingerprint"] == "F" * 40
    assert saved["uid"] == "Escrow <escrow@example.lab>"
    assert s.target.escrow_saved_by == "bryan@example.lab"
    assert state["escrow_key"]["fingerprint"] == "F" * 40
    with _engine(), pytest.raises(escrow.EscrowKeyRefused, match="SECRET"):
        escrow.save_escrow_key(session, s.target, SECRET, "bryan@example.lab")
    assert "PRIVATE" not in (s.target.escrow_public_key or "")


def test_a_key_gpg_refuses_is_refused_with_its_reason(session):
    s = _setup(session)

    def refuse(_key):
        raise ValueError("gpg could not read that public key")

    with patch.object(escrow, "backup_engine",
                      return_value=SimpleNamespace(inspect_recipient=refuse)):  # fmt: skip
        with pytest.raises(escrow.EscrowKeyRefused, match="gpg could not read"):
            escrow.save_escrow_key(session, s.target, PUBLIC, "x@y.lab")
    assert s.target.escrow_fingerprint is None


def _manager(session, email, admin=False):
    user = models.User(id=uuid.uuid4(), userid=email, active=True, is_admin=admin)
    session.add(user)
    session.flush()
    return user


def test_a_scheduled_rotation_emails_the_backup_managers(session):
    _setup(session)
    _manager(session, "admin@example.lab", admin=True)
    mailer = MagicMock()
    mailer.is_enabled.return_value = True
    mailer.send_email.return_value = True
    with patch("backend.services.email_service.email_service", mailer), \
            patch("backend.services.audit_service.AuditService.log") as audit:  # fmt: skip
        assert escrow.remind_after_rotation(session, 2)
    recipients, subject, body = mailer.send_email.call_args.args[:3]
    assert recipients == ["admin@example.lab"]
    assert "break-glass" in subject and "2" in body
    assert audit.call_args.kwargs["description"] == escrow.REMINDER_AUDIT
    assert audit.call_args.kwargs["details"]["rotated"] == 2


def test_no_email_when_email_is_off_or_nothing_rotated(session):
    _setup(session)
    _manager(session, "admin@example.lab", admin=True)
    mailer = MagicMock()
    mailer.is_enabled.return_value = False
    with patch("backend.services.email_service.email_service", mailer):
        assert not escrow.remind_after_rotation(session, 2)
        mailer.is_enabled.return_value = True
        assert not escrow.remind_after_rotation(session, 0)
    mailer.send_email.assert_not_called()


def test_the_tick_reminds_after_it_rotates(session):
    s = _setup(session)
    _encrypt(session, s)
    engine = SimpleNamespace(rotate_due=lambda *a, **k: 1)
    with patch.object(backup_tick, "_encryption_engine", return_value=engine), \
            patch.object(escrow, "remind_after_rotation") as remind:  # fmt: skip
        assert backup_tick.rotate_keys(session, s.target, WHEN) == 1
    remind.assert_called_once_with(session, 1)


@pytest.mark.asyncio
async def test_saving_the_key_needs_the_engine_and_refuses_a_secret_key(session):
    s = _setup(session)
    user = SimpleNamespace(
        id=None, userid="bryan@example.lab", has_role=lambda role: True
    )
    with patch.object(escrow, "backup_engine", return_value=None):
        with pytest.raises(HTTPException) as no_engine:
            await api.save_escrow_key(
                api.EscrowKeyBody(public_key=PUBLIC), session, user
            )
    assert no_engine.value.status_code == 402
    with _engine(), patch.object(api, "_audit") as audit:
        with pytest.raises(HTTPException) as secret:
            await api.save_escrow_key(
                api.EscrowKeyBody(public_key=SECRET), session, user
            )
        assert secret.value.status_code == 422
        saved = await api.save_escrow_key(
            api.EscrowKeyBody(public_key=PUBLIC), session, user
        )
    audit.assert_called_once()  # the refused secret key was never audited as saved
    assert audit.call_args.args[5] == "Backup break-glass escrow key saved"
    assert saved["fingerprint"] == "F" * 40 and s.target.escrow_fingerprint == "F" * 40
