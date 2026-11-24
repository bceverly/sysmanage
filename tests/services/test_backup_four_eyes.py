# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Four-eyes restore approval (ROADMAP 27.2, Enterprise backup_ops_engine):
with the setting on, a restore over a host's own files waits for a second
person with the restore role; the approval sends exactly what was asked."""

# pylint: disable=redefined-outer-name,unused-argument

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest

from backend.api import backups as api
from backend.api import backups_four_eyes as eyes_api
from backend.persistence import models
from backend.security.roles import SecurityRoles
from backend.services import backup_four_eyes as four_eyes
from backend.services import backup_jobs as jobs
from tests.services.test_backup_results import _setup
from tests.test_backups_api import (  # noqa: F401  pylint: disable=unused-import
    MANAGER,
    _status,
    _unsigned_snapshot,
    sent,
)


def _person(userid, *roles):
    return SimpleNamespace(
        id=uuid.uuid4(), userid=userid, has_role=lambda r: r in roles
    )


ALICE = _person(
    "alice@example.com", SecurityRoles.RESTORE_FILES, SecurityRoles.MANAGE_BACKUPS
)
BOB = _person("bob@example.com", SecurityRoles.RESTORE_FILES)
CAROL = _person("carol@example.com")  # no restore role


@pytest.fixture
def ops_engine(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("backup_ops_engine")
    monkeypatch.setattr(four_eyes, "engine", lambda: eng)
    return eng


@pytest.fixture
def setting(monkeypatch):
    state = {"on": True}
    monkeypatch.setattr(four_eyes, "enabled", lambda: state["on"])
    monkeypatch.setattr(four_eyes, "set_enabled", lambda v: state.update(on=bool(v)))
    return state


def _in_place(session):
    s = _setup(session)
    name = _unsigned_snapshot(session, s)
    body = api.RestoreBody(snapshot=name, include=["/etc/nginx"], in_place=True,
                           dry_run=False, acknowledge_in_place=True,
                           acknowledge_unsigned=True)  # fmt: skip
    return s, body


def _restores(sent):
    return [c for c in sent if c[1] == "backup_restore"]


def test_a_restore_in_place_waits_for_a_second_person(
    session, sent, ops_engine, setting
):
    s, body = _in_place(session)
    held = api.backup_restore(str(s.host.id), body, session, ALICE)
    assert held["status"] == four_eyes.AWAITING
    assert _restores(sent) == []  # nothing reached the host
    request = session.get(models.BackupRestoreRequest, uuid.UUID(held["request_id"]))
    assert request.status == "pending" and request.requested_by == ALICE.userid

    out = eyes_api.approve_restore(held["request_id"], session, BOB)

    assert _restores(sent)[-1][2]["in_place"] is True
    assert _restores(sent)[-1][2]["include"] == ["/etc/nginx"]
    request = session.get(models.BackupRestoreRequest, request.id)
    assert request.status == "approved" and request.decided_by == BOB.userid
    assert str(request.run_id) == out["id"]


@pytest.mark.asyncio
async def test_the_requester_cannot_approve_and_others_need_the_role(
    session, sent, ops_engine, setting
):
    s, body = _in_place(session)
    held = api.backup_restore(str(s.host.id), body, session, ALICE)
    rid = held["request_id"]
    assert await _status(lambda: eyes_api.approve_restore(rid, session, ALICE)) == 403
    assert await _status(lambda: eyes_api.approve_restore(rid, session, CAROL)) == 403
    assert _restores(sent) == []
    eyes_api.approve_restore(rid, session, BOB)
    assert await _status(lambda: eyes_api.approve_restore(rid, session, BOB)) == 409


def test_staging_and_previews_never_wait(session, sent, ops_engine, setting):
    s, body = _in_place(session)
    preview = body.model_copy(update={"dry_run": True})
    assert (
        api.backup_restore(str(s.host.id), preview, session, ALICE)["action"]
        == "restore"
    )
    staged = body.model_copy(update={"in_place": False})
    assert (
        api.backup_restore(str(s.host.id), staged, session, ALICE)["action"]
        == "restore"
    )
    assert len(_restores(sent)) == 2


def test_with_the_setting_off_nothing_waits(session, sent, ops_engine, setting):
    setting["on"] = False
    s, body = _in_place(session)
    out = api.backup_restore(str(s.host.id), body, session, ALICE)
    assert out["action"] == "restore" and len(_restores(sent)) == 1


def test_without_the_engine_nothing_waits(session, sent, monkeypatch, setting):
    monkeypatch.setattr(four_eyes, "engine", lambda: None)
    s, body = _in_place(session)
    assert (
        api.backup_restore(str(s.host.id), body, session, ALICE)["action"] == "restore"
    )


@pytest.mark.asyncio
async def test_reject_and_withdraw(session, sent, ops_engine, setting):
    s, body = _in_place(session)
    first = api.backup_restore(str(s.host.id), body, session, ALICE)["request_id"]
    second = api.backup_restore(str(s.host.id), body, session, ALICE)["request_id"]
    reason = eyes_api.RejectBody(reason="wrong snapshot")
    assert (
        await _status(lambda: eyes_api.reject_restore(first, reason, session, ALICE))
        == 403
    )
    eyes_api.reject_restore(first, reason, session, BOB)
    assert (
        session.get(models.BackupRestoreRequest, uuid.UUID(first)).reason
        == "wrong snapshot"
    )
    assert await _status(lambda: eyes_api.withdraw_restore(second, session, BOB)) == 403
    eyes_api.withdraw_restore(second, session, ALICE)
    assert (
        session.get(models.BackupRestoreRequest, uuid.UUID(second)).status
        == "withdrawn"
    )
    assert _restores(sent) == []


@pytest.mark.asyncio
async def test_an_old_request_expires(session, sent, ops_engine, setting):
    s, body = _in_place(session)
    rid = api.backup_restore(str(s.host.id), body, session, ALICE)["request_id"]
    request = session.get(models.BackupRestoreRequest, uuid.UUID(rid))
    request.requested_at = jobs.now() - timedelta(
        hours=ops_engine.REQUEST_TTL_HOURS + 1
    )
    session.commit()
    assert await _status(lambda: eyes_api.approve_restore(rid, session, BOB)) == 409
    listed = eyes_api.get_four_eyes(session)["requests"]
    assert listed[0]["status"] == "expired"
    assert session.get(models.BackupRestoreRequest, uuid.UUID(rid)).status == "expired"


@pytest.mark.asyncio
async def test_the_setting_needs_the_role_and_the_engine(session, monkeypatch, setting):
    monkeypatch.setattr(four_eyes, "engine", lambda: None)
    assert await _status(lambda: eyes_api.get_four_eyes(session)) == 402
    assert (
        await _status(
            lambda: eyes_api.put_four_eyes(
                eyes_api.FourEyesBody(enabled=True), session, ALICE
            )
        )
        == 402
    )
    monkeypatch.setattr(four_eyes, "engine", object)
    assert (
        await _status(
            lambda: eyes_api.put_four_eyes(
                eyes_api.FourEyesBody(enabled=False), session, BOB
            )
        )
        == 403
    )
    assert eyes_api.put_four_eyes(
        eyes_api.FourEyesBody(enabled=False), session, ALICE
    ) == {"enabled": False}


def test_the_setting_is_off_until_turned_on(monkeypatch):
    stored = {}
    monkeypatch.setattr(four_eyes, "_tenant", lambda: None)
    monkeypatch.setattr(four_eyes.settings_service, "get_setting", stored.get)
    monkeypatch.setattr(
        four_eyes.settings_service, "set_setting", lambda k, v: stored.update({k: v})
    )
    assert four_eyes.enabled() is False
    four_eyes.set_enabled(True)
    assert four_eyes.enabled() is True and stored == {"backup_four_eyes": True}


# --- any kind of request (2026-11-24) ---------------------------------------


@pytest.fixture
def clone_kind(monkeypatch):
    """A stand-in for the rebuild / clone kinds still to come: approvable
    only with Manage Backups, and recording what approving it ran."""
    ran = []

    def perform(db, user, request, host):
        ran.append((user.userid, request.kind, str(host.id)))
        return {"id": str(uuid.uuid4())}

    kind = four_eyes.Kind(
        role=SecurityRoles.MANAGE_BACKUPS,
        perform=perform,
        refusals={"no_role": lambda: "Permission denied: Manage Backups role required"},
    )
    monkeypatch.setitem(four_eyes.KINDS, "clone", kind)
    return ran


def _hold_clone(session, host):
    return four_eyes.hold_request(
        session, ALICE, host, kind="clone", payload={"snapshot": "s1"},
        facts={}, audit_text="Clone requested", target={"hypervisor": "kvm01"},
    )  # fmt: skip


@pytest.mark.asyncio
async def test_another_kind_is_held_and_approved_through_its_own_rules(
    session, sent, ops_engine, setting, clone_kind
):
    s = _setup(session)
    held = _hold_clone(session, s.host)
    assert held["status"] == four_eyes.AWAITING and held["kind"] == "clone"
    rid = held["request_id"]
    # BOB can restore files but not manage backups: this kind's role decides.
    assert await _status(lambda: eyes_api.approve_restore(rid, session, BOB)) == 403
    assert clone_kind == []
    carol = _person("carol@example.com", SecurityRoles.MANAGE_BACKUPS)
    out = eyes_api.approve_restore(rid, session, carol)
    assert clone_kind == [(carol.userid, "clone", str(s.host.id))]
    request = session.get(models.BackupRestoreRequest, uuid.UUID(rid))
    assert request.status == "approved" and str(request.run_id) == out["id"]
    listed = four_eyes.recent(session, ops_engine, jobs.now())
    assert listed[0]["kind"] == "clone" and listed[0]["target"] == {
        "hypervisor": "kvm01"
    }


@pytest.mark.asyncio
async def test_a_kind_this_server_cannot_perform_is_never_marked_approved(
    session, sent, ops_engine, setting
):
    s = _setup(session)
    request = models.BackupRestoreRequest(
        host_id=s.host.id, kind="teleport", body="{}", status="pending",
        requested_by=ALICE.userid, requested_at=jobs.now(),
    )  # fmt: skip
    session.add(request)
    session.commit()
    rid = str(request.id)
    assert await _status(lambda: eyes_api.approve_restore(rid, session, BOB)) == 409
    assert session.get(models.BackupRestoreRequest, request.id).status == "pending"


def test_an_engine_from_before_kinds_still_decides(monkeypatch, setting):
    old = SimpleNamespace(
        restore_needs_approval=lambda on, in_place, dry: on and in_place and not dry
    )
    assert four_eyes.needs_approval(old, "restore", {"in_place": True}) is True
    assert four_eyes.needs_approval(old, "restore", {"in_place": False}) is False
    assert four_eyes.needs_approval(old, "clone", {}) is True
    assert four_eyes.needs_approval(old, "clone", {"dry_run": True}) is False
    setting["on"] = False
    assert four_eyes.needs_approval(old, "clone", {}) is False
