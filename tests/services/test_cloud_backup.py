# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""iCloud Photos to local (24.12): enable on the storage host, accounts whose
password lives only in OpenBAO, the two-factor relay, results ("Needs
sign-in" is never "no new photos"), the schedule sharing the target's cap,
the sign-in expiry warning, and the air gap hiding all of it."""

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import agent_cloud_backup as agent_api
from backend.api import cloud_backup as api
from backend.persistence import models
from backend.security.roles import SecurityRoles
from backend.services import cloud_backup_jobs as cloud
from backend.services import cloud_backup_results as results
from backend.services import cloud_backup_secrets as secrets
from backend.services import cloud_backup_tick as tick
from backend.services import cloud_backup_views as views
from backend.services import maintenance_command_classes as windows
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)

PASSWORD = "correct-horse-battery-staple"  # nosec B105  # a test value


def _user(*roles):
    return SimpleNamespace(
        id=uuid.uuid4(), userid="ops@example.com", has_role=lambda r: r in roles
    )


MANAGER = _user(SecurityRoles.MANAGE_CLOUD_BACKUPS)
BACKUPS_ONLY = _user(SecurityRoles.MANAGE_BACKUPS)


class _Vault:
    def __init__(self):
        self.store, self.deleted = {}, []

    def store_secret(self, secret_name, secret_data, secret_type, secret_subtype=None):
        path = f"secret/data/secrets/{secret_type}/{secret_subtype}/{uuid.uuid4()}"
        self.store[path] = secret_data
        return {"vault_path": path}

    def retrieve_secret(self, path):
        return {"content": self.store[path]}

    def delete_secret(self, path):
        self.deleted.append(path)
        self.store.pop(path, None)
        return True


@pytest.fixture(autouse=True)
def online(monkeypatch):
    monkeypatch.setattr(cloud, "airgapped", lambda: False)


@pytest.fixture
def vault(monkeypatch):
    fake = _Vault()
    monkeypatch.setattr(secrets, "_vault", lambda vault=None: vault or fake)
    return fake


async def _status(coro):
    with pytest.raises(HTTPException) as caught:
        await coro
    return caught.value.status_code


def _enabled(session, s):
    session.add(
        models.CloudBackupEnable(
            target_id=s.target.id, host_id=s.nas.id, status=cloud.OK,
            tool_version="1.32.3", install_method="binary",
        )
    )  # fmt: skip
    session.commit()


async def _account(session, **extra):
    body = api.AccountCreate(
        apple_id="family@example.com", display_name="Family", password=PASSWORD,
        **extra,
    )  # fmt: skip
    made = await api.cloud_account_create(body, session, MANAGER)
    return session.query(models.CloudBackupAccount).filter_by(id=made["id"]).one()


# --- enable ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_goes_to_the_storage_host_only(session, sent):
    s = _setup(session)
    assert await _status(api.cloud_enable(session, BACKUPS_ONLY)) == 403
    answer = await api.cloud_enable(session, MANAGER)
    assert sent[-1][0] == str(s.nas.id)  # never the backed-up host
    assert sent[-1][1] == "cloud_backup_enable"
    assert sent[-1][2]["storage_path"] == "/srv/backups/restate"
    assert answer["enable"]["status"] == "running"
    assert answer["storage_host"]["fqdn"] == "nas.lab"
    # A second press while it runs is refused; once it ended, it repairs.
    assert await _status(api.cloud_enable(session, MANAGER)) == 409
    run = session.query(models.CloudBackupRun).one()
    with patch("backend.services.agent_capability_service.request_refresh") as ask:
        results.record_result(
            session, s.nas.id,
            {"run_id": str(run.id), "status": "ok", "tool_version": "1.32.3",
             "install_method": "venv", "cloud_root": "/srv/backups/restate/cloud-photos"},
        )  # fmt: skip
    ask.assert_called_once()  # the agent now advertises cloud_backup_run
    session.commit()
    assert cloud.enabled(session, s.target.id)
    again = await api.cloud_enable(session, MANAGER)
    assert again["enable"]["status"] == "running"


@pytest.mark.asyncio
async def test_a_failed_enable_keeps_the_tools_reason(session, sent):
    s = _setup(session)
    await api.cloud_enable(session, MANAGER)
    run = session.query(models.CloudBackupRun).one()
    results.record_result(
        session, s.nas.id,
        {"run_id": str(run.id), "status": "failed", "reason": "checksum_mismatch",
         "detail": "sha256 did not match"},
    )  # fmt: skip
    row = cloud.enable_row(session, s.target.id)
    assert (row.status, row.reason, row.detail) == (
        "failed",
        "checksum_mismatch",
        "sha256 did not match",
    )


# --- accounts and the password ----------------------------------------------------


@pytest.mark.asyncio
async def test_the_password_is_only_in_openbao(session, sent, vault):
    s = _setup(session)
    _enabled(session, s)
    with patch.object(api.AuditService, "log") as audit:
        account = await _account(session)
    assert account.password_ref in vault.store
    assert vault.store[account.password_ref] == PASSWORD
    assert "/cloud_backup/server/" in account.password_ref  # the tenant's path
    row = {c.name: getattr(account, c.name) for c in account.__table__.columns}
    assert PASSWORD not in json.dumps(row, default=str)
    assert PASSWORD not in json.dumps(audit.call_args.kwargs, default=str)
    shown = views.account_dict(session, account)
    assert PASSWORD not in json.dumps(shown) and shown["password_set"] is True
    assert account.dir_name == cloud.dir_name_for(account.id)


@pytest.mark.asyncio
async def test_account_rules(session, sent, vault):
    s = _setup(session)
    _enabled(session, s)
    bad = api.AccountCreate(apple_id="not-an-email", display_name="x", password="p")
    assert await _status(api.cloud_account_create(bad, session, MANAGER)) == 422
    await _account(session)
    dup = api.AccountCreate(
        apple_id="FAMILY@example.com", display_name="y", password="p"
    )
    assert await _status(api.cloud_account_create(dup, session, MANAGER)) == 409


@pytest.mark.asyncio
async def test_a_new_password_replaces_the_old_in_openbao(session, sent, vault):
    s = _setup(session)
    _enabled(session, s)
    account = await _account(session)
    old = account.password_ref
    body = api.AccountUpdate(display_name="Family", password="new-one")
    await api.cloud_account_update(str(account.id), body, session, MANAGER)
    assert account.password_ref != old and old in vault.deleted
    assert vault.store[account.password_ref] == "new-one"


@pytest.mark.asyncio
async def test_deleting_removes_the_sign_in_and_password_keeps_photos(
    session, sent, vault
):
    s = _setup(session)
    _enabled(session, s)
    account = await _account(session)
    reference, dir_name = account.password_ref, account.dir_name
    answer = await api.cloud_account_delete(str(account.id), session, MANAGER)
    assert answer == {"deleted": True, "photos_kept": True}
    assert sent[-1][:2] == (str(s.nas.id), "cloud_backup_remove")
    assert sent[-1][2]["dir_name"] == dir_name
    assert reference in vault.deleted
    assert session.query(models.CloudBackupAccount).count() == 0


# --- sign-in, the password release and the code relay ----------------------------


@pytest.mark.asyncio
async def test_connect_releases_the_password_once_and_relays_the_code(
    session, sent, vault
):
    s = _setup(session)
    _enabled(session, s)
    account = await _account(session)
    run = await api.cloud_account_connect(str(account.id), session, MANAGER)
    command = sent[-1]
    assert command[:2] == (str(s.nas.id), "cloud_backup_run")
    assert command[2]["action"] == "connect"
    assert PASSWORD not in json.dumps(command)  # never through the queue
    # Another host gets nothing, and learns nothing.
    with pytest.raises(secrets.SecretRefused) as other:
        secrets.release_password(session, s.host.id, run["id"])
    assert other.value.status == 404
    assert secrets.release_password(session, s.nas.id, run["id"]) == PASSWORD
    with pytest.raises(secrets.SecretRefused):
        secrets.release_password(session, s.nas.id, run["id"])  # once per run
    # The job waits for a code; nobody has typed one yet.
    assert secrets.release_code(session, s.nas.id, run["id"]) is None
    row = session.query(models.CloudBackupRun).filter_by(id=uuid.UUID(run["id"])).one()
    assert row.status == "waiting_code"
    assert views.account_dict(session, account)["status"] == "waiting_code"
    bad = api.CodeBody(code="12345x")
    assert await _status(api.cloud_run_code(run["id"], bad, session, MANAGER)) == 422
    with patch.object(api.AuditService, "log") as audit:
        await api.cloud_run_code(
            run["id"], api.CodeBody(code="123 456"), session, MANAGER
        )
    assert "123456" not in json.dumps(audit.call_args.kwargs, default=str)
    assert secrets.release_code(session, s.nas.id, run["id"]) == "123456"
    assert row.mfa_code is None and row.status == "running"  # cleared once handed over
    results.record_result(session, s.nas.id, {"run_id": run["id"], "status": "ok"})
    session.flush()  # the handler commits
    assert account.session_created_at is not None
    assert views.account_dict(session, account)["status"] == "ok"


def test_a_code_too_late_is_refused(session, sent, vault):
    s = _setup(session)
    _enabled(session, s)
    account = models.CloudBackupAccount(
        target_id=s.target.id, apple_id="a@example.com", display_name="A",
        dir_name="icloud-0000abcd", password_ref="x",
    )  # fmt: skip
    session.add(account)
    session.flush()
    run = cloud.queue_account_run(session, account, cloud.CONNECT, "ops")
    run.status, run.code_requested_at = "waiting_code", cloud.now() - timedelta(hours=1)
    with pytest.raises(cloud.CloudBackupRefused):
        secrets.submit_code(session, run, "123456")
    with pytest.raises(secrets.SecretRefused):
        secrets.release_code(session, s.nas.id, run.id)


@pytest.mark.asyncio
async def test_the_secret_endpoint_answers_no_store_and_audits(session, sent, vault):
    s = _setup(session)
    _enabled(session, s)
    account = await _account(session)
    run = await api.cloud_account_connect(str(account.id), session, MANAGER)
    body = agent_api.RunRequest(host_id=str(s.nas.id), run_id=run["id"])
    with patch.object(agent_api, "_authenticated_host_id", return_value=str(s.nas.id)), \
            patch.object(agent_api, "_verify_host"), \
            patch.object(agent_api, "_host_session", return_value=session), \
            patch.object(agent_api.AuditService, "log") as audit:  # fmt: skip
        answer = await agent_api.agent_cloud_backup_secret(
            None, body, "Bearer t", "h", session
        )
    assert json.loads(answer.body) == {"password": PASSWORD}
    assert answer.headers["cache-control"] == "no-store"
    assert audit.call_args.kwargs["details"] == {"run_id": run["id"]}
    assert PASSWORD not in json.dumps(audit.call_args.kwargs, default=str)


# --- results ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_auth_failure_is_needs_sign_in_never_no_new_photos(
    session, sent, vault
):
    s = _setup(session)
    _enabled(session, s)
    account = await _account(session)
    account.session_created_at = cloud.now() - timedelta(days=3)
    run = cloud.queue_account_run(session, account, cloud.DOWNLOAD, "ops")
    results.record_result(
        session, s.nas.id,
        {"run_id": str(run.id), "status": "needs_sign_in", "exit_code": 1,
         "message": "Apple asked for a sign-in", "downloaded": 0},
    )  # fmt: skip
    session.flush()  # the handler commits
    shown = views.account_dict(session, account)
    assert shown["status"] == "needs_sign_in"
    assert shown["last_good_at"] is None
    assert views.summary(session)["needs_sign_in"] == 1
    # Not started on schedule (it would only fail again).
    assert not tick.due(session, account, cloud.now() + timedelta(days=2))


@pytest.mark.asyncio
async def test_a_good_download_records_its_counts(session, sent, vault):
    s = _setup(session)
    _enabled(session, s)
    account = await _account(session)
    account.session_created_at = cloud.now()
    run = cloud.queue_account_run(session, account, cloud.RECONCILE, "ops")
    results.record_progress(session, s.nas.id, {"run_id": str(run.id), "downloaded": 7})
    assert run.status == "running"
    results.record_result(
        session, s.nas.id,
        {"run_id": str(run.id), "status": "ok", "exit_code": 0, "downloaded": 12,
         "present": 3, "failed": 1, "bytes": 4096, "duration": 30,
         "photos_local": 15, "bytes_local": 9000},
    )  # fmt: skip
    session.flush()  # the handler commits
    shown = views.account_dict(session, account)
    assert shown["last_run"]["downloaded"] == 12
    assert shown["last_run"]["failed"] == 1 and shown["last_run"]["bytes"] == 4096
    assert account.last_full_at is not None and shown["photos_local"] == 15


def test_a_result_from_another_host_is_ignored(session, sent):
    s = _setup(session)
    _enabled(session, s)
    run = cloud.queue_enable(session, s.target, s.nas, "ops")
    assert results.record_result(session, s.host.id, {"run_id": str(run.id),
                                                      "status": "ok"}) is None  # fmt: skip
    assert run.status == "queued"


# --- the schedule -------------------------------------------------------------------


def _signed_in(session, s, **extra):
    values = {
        "target_id": s.target.id, "apple_id": "a@example.com", "display_name": "A",
        "dir_name": "icloud-0000abcd", "password_ref": "x",
        "session_created_at": cloud.now() - timedelta(days=1),
        "created_at": cloud.now(), **extra,
    }  # fmt: skip
    account = models.CloudBackupAccount(**values)
    session.add(account)
    session.commit()
    return account


def test_first_a_full_pass_then_incremental_then_weekly_full(session, sent):
    s = _setup(session)
    _enabled(session, s)
    account = _signed_in(session, s)
    now = cloud.now()
    assert tick.transfer_action(account, now) == cloud.RECONCILE
    account.last_full_at = now - timedelta(days=2)
    assert tick.transfer_action(account, now) == cloud.DOWNLOAD
    account.last_full_at = now - timedelta(days=8)
    assert tick.transfer_action(account, now) == cloud.RECONCILE


def test_the_tick_starts_due_downloads_on_the_storage_host(session, sent):
    s = _setup(session)
    _enabled(session, s)
    account = _signed_in(session, s, last_full_at=cloud.now())
    assert tick.reconcile(session, s.target, cloud.now()) == 1
    assert sent[-1][:2] == (str(s.nas.id), "cloud_backup_run")
    assert sent[-1][2]["action"] == "download"
    assert sent[-1][2]["until_found"] == 50
    assert "auto_delete" not in sent[-1][2]  # one-way: nothing that deletes
    assert tick.reconcile(session, s.target, cloud.now()) == 0  # already running
    assert account.run_requested_at is None


def test_downloads_share_the_targets_cap(session, sent):
    s = _setup(session)  # max_concurrent=2
    _enabled(session, s)
    for index in range(3):
        _signed_in(session, s, apple_id=f"a{index}@example.com",
                   dir_name=f"icloud-0000abc{index}")  # fmt: skip
    assert tick.reconcile(session, s.target, cloud.now()) == 2
    from backend.services import backup_tick  # noqa: PLC0415

    assert backup_tick.running_captures(session, s.target.id) == 2


def test_not_enabled_never_signed_in_or_off_window_is_not_started(session, sent):
    s = _setup(session)
    account = _signed_in(session, s)
    assert tick.reconcile(session, s.target, cloud.now()) == 0  # not enabled
    _enabled(session, s)
    account.session_created_at = None
    assert not tick.due(session, account, cloud.now())
    account.session_created_at = cloud.now()
    now = datetime(2026, 11, 3, 12, 0)
    account.window_start_hour = 1
    assert not tick.due(session, account, now)
    assert tick.due(session, account, now.replace(hour=2))


def test_the_sign_in_expiry_warns_once(session, sent):
    s = _setup(session)
    _enabled(session, s)
    account = _signed_in(session, s)
    account.session_created_at = cloud.now() - timedelta(days=55)
    with patch.object(tick, "_email", return_value=False) as mail:
        assert tick.warn_expiring(session, s.target.id, cloud.now()) == 1
        assert tick.warn_expiring(session, s.target.id, cloud.now()) == 0
    mail.assert_called_once()
    assert views.account_dict(session, account)["session_expiring"] is True
    assert views.summary(session)["expiring"] == 1


def test_a_long_download_that_reports_is_not_stuck(session, sent):
    s = _setup(session)
    _enabled(session, s)
    account = _signed_in(session, s)
    run = cloud.queue_account_run(session, account, cloud.RECONCILE, "ops")
    run.queued_at = cloud.now() - timedelta(days=2)
    results.record_progress(session, s.nas.id, {"run_id": str(run.id), "downloaded": 9})
    assert tick.fail_stuck(session, cloud.now()) == 0
    assert tick.fail_stuck(session, cloud.now() + timedelta(hours=4)) == 1


def test_a_stuck_run_is_failed(session, sent):
    s = _setup(session)
    _enabled(session, s)
    account = _signed_in(session, s)
    run = cloud.queue_account_run(session, account, cloud.DOWNLOAD, "ops")
    run.queued_at = cloud.now() - timedelta(hours=13)
    assert tick.fail_stuck(session, cloud.now()) == 1
    assert run.status == "failed"


# --- the air gap, windows and routing --------------------------------------------


@pytest.mark.asyncio
async def test_an_air_gapped_server_hides_it(session, sent, monkeypatch):
    s = _setup(session)
    _enabled(session, s)
    monkeypatch.setattr(cloud, "airgapped", lambda: True)
    assert (await api.cloud_overview(session)) == {
        "available": False,
        "reason": "airgapped",
    }
    assert await _status(api.cloud_enable(session, MANAGER)) == 404
    assert views.summary(session)["enabled"] is False
    assert tick.reconcile(session, s.target, cloud.now()) == 0


def test_maintenance_windows_hold_changes_not_a_sign_in():
    def envelope(command, action):
        return json.dumps({"data": {"command_type": command,
                                    "parameters": {"action": action}}})  # fmt: skip

    assert windows.is_window_gated("command", envelope("cloud_backup_enable", None))
    assert windows.is_window_gated("command", envelope("cloud_backup_run", "download"))
    assert not windows.is_window_gated(
        "command", envelope("cloud_backup_run", "connect")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message_type, handler",
    [
        ("cloud_backup_result", "handle_cloud_backup_result"),
        ("cloud_backup_progress", "handle_cloud_backup_progress"),
    ],
)
async def test_results_are_routed(session, message_type, handler):
    from unittest.mock import AsyncMock  # noqa: PLC0415

    from backend.websocket import message_router  # noqa: PLC0415

    with patch.object(message_router, handler, new=AsyncMock()) as called:
        assert await message_router.route_inbound_message(
            message_type, session, SimpleNamespace(host_id="h"), {"run_id": "x"}
        )
    called.assert_awaited_once()
