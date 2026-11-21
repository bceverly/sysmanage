# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Off-site copies (27.3): the source storage host copies each snapshot
into a repository behind the off-site target's restate-proxy, with a token
of its own and an append-only grant; the off-site storage host prepares,
protects, prunes (the source's retention and holds) and sizes the copy."""

import json

import pytest
import uuid
from datetime import datetime

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_replicas as replicas
from backend.services import backup_results as results
from tests.services.test_backup_results import (  # noqa: F401  pylint: disable=unused-import
    _host,
    _result,
    _setup,
    sent,
)

TOKEN = "a" * 64
NEW_TOKEN = "b" * 64


def _offsite(session, s):
    """An off-site target behind restate-proxy on another storage host, and
    the source target copying to it."""
    nas2 = _host(session, fqdn="nas.dc2.lab")
    stamp = datetime(2026, 11, 1)
    holder = models.BackupTarget(
        id=uuid.uuid4(),
        name="Offsite",
        location="DC2",
        host_mount_point="/mnt/offsite",
        storage_host_id=nas2.id,
        storage_path="/srv/offsite/restate",
        max_concurrent=2,
        seal_mode="none",
        transport="proxy",
        proxy_host="backup.dc2.lab",
        proxy_port=8443,
        proxy_pin_sha256="c" * 64,
        created_at=stamp,
        updated_at=stamp,
    )
    session.add(holder)
    s.target.replica_target_id = holder.id
    s.policy.storage_abilities = json.dumps(["replica_copy"])
    session.commit()
    s.holder, s.nas2 = holder, nas2
    return s


def _snapshot(session, s, name, gone=False):
    session.add(
        models.BackupSnapshot(
            id=uuid.uuid4(),
            policy_id=s.policy.id,
            host_id=s.host.id,
            name=name,
            seen_at=datetime(2026, 11, 20),
            gone_at=datetime(2026, 11, 20) if gone else None,
        )
    )
    session.commit()


def _runs(session, action):
    return (
        session.query(models.BackupRun)
        .filter(models.BackupRun.action == action)
        .order_by(models.BackupRun.queued_at)
        .all()
    )


def _ack(session, run, reply=None):
    results.record_command_result(
        session, {"command_id": run.command_id, "success": True, "result": reply or {}}
    )
    session.commit()


def _finish(session, run, status="ok", **result):
    results.record_result(session, run.host_id, _result(run, status, **result))
    session.commit()


def _ready_row(session, s, sent):  # noqa: F811
    """Configured both sides, token in the grant, repository prepared."""
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    _ack(session, _runs(session, jobs.CONFIGURE)[-1],
         {"copy_tokens": {str(replicas.rows(session, s.policy)[0].id): TOKEN}})  # fmt: skip
    replicas.configure_pending(session)
    session.commit()
    _ack(session, _runs(session, "off_configure")[-1], {"abilities": ["keep_snapshot"]})
    _finish(session, _runs(session, "off_prepare")[-1])
    return replicas.rows(session, s.policy)[0]


def test_the_source_storage_host_is_told_where_to_copy(session, sent):  # noqa: F811
    s = _offsite(session, _setup(session))
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    row = replicas.rows(session, s.policy)[0]
    payload = sent[-1][2]
    assert payload["replicas"] == [{
        "id": str(row.id),
        "url": f"https://backup.dc2.lab:8443/v1/replica-{row.id}",
        "pin_sha256": "c" * 64,
    }]  # fmt: skip
    assert row.repo_dir == jobs.policy_repo_dir(s.policy, s.host)


def test_an_older_storage_agent_is_not_sent_replicas(session, sent):  # noqa: F811
    s = _offsite(session, _setup(session))
    s.policy.storage_abilities = json.dumps([])
    session.commit()
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert "replicas" not in sent[-1][2]


def test_the_copy_token_goes_into_an_append_only_offsite_grant(
    session, sent
):  # noqa: F811
    s = _offsite(session, _setup(session))
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    row = replicas.rows(session, s.policy)[0]
    _ack(
        session,
        _runs(session, jobs.CONFIGURE)[-1],
        {"copy_tokens": {str(row.id): TOKEN}},
    )
    assert row.token_sha256 == TOKEN
    replicas.configure_pending(session)
    session.commit()
    run = _runs(session, "off_configure")[-1]
    assert str(run.host_id) == str(s.nas2.id)
    payload = sent[-1][2]
    assert payload["policy_id"] == str(row.id) and payload["role"] == "storage"
    assert payload["target"]["mount_point"] == "/srv/offsite/restate"
    block = payload["target"]["proxy"]
    assert block["export"] is False
    assert block["grants"] == [
        {
            "client": f"replica-{row.id}",
            "token_sha256": [TOKEN],
            "operations": ["append"],
        }
    ]
    assert f"replica-{row.id}" in block["clients"]
    assert payload["jobs"]["prune"]["keep_last"] == 14
    assert "encrypt_key" not in payload


def test_no_offsite_configure_before_the_token(session, sent):  # noqa: F811
    s = _offsite(session, _setup(session))
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    replicas.configure_pending(session)
    assert _runs(session, "off_configure") == []


def test_the_copy_runs_oldest_first_then_the_offsite_chain(session, sent):  # noqa: F811
    s = _offsite(session, _setup(session))
    _snapshot(session, s, "20261120T010000Z")
    _snapshot(session, s, "20261119T010000Z")
    _snapshot(session, s, "20261101T010000Z", gone=True)
    row = _ready_row(session, s, sent)
    assert row.prepared_at is not None
    copy = _runs(session, "copy")[-1]
    assert str(copy.host_id) == str(s.nas.id)
    assert sent[-1][2]["snapshot"] == "20261119T010000Z"
    assert sent[-1][2]["policy_id"] == str(s.policy.id)
    _finish(session, copy, copy={"snapshot": "20261119T010000Z", "packs_copied": 3})
    copy = _runs(session, "copy")[-1]
    assert sent[-1][2]["snapshot"] == "20261120T010000Z"
    _finish(session, copy, copy={"snapshot": "20261120T010000Z"})
    protect = _runs(session, "off_protect")[-1]
    assert str(protect.host_id) == str(s.nas2.id)
    assert sent[-1][2] == {"run_id": str(protect.id), "policy_id": str(row.id),
                           "action": "protect"}  # fmt: skip
    _finish(session, protect)
    _finish(session, _runs(session, "off_prune")[-1], pruned=["20261119T010000Z"])
    assert replicas.needed(session, row) == []  # dropped off-site: never again
    _finish(session, _runs(session, "off_du")[-1], du={
        "bytes": 1234, "snapshots": [{"name": "20261120T010000Z"}]})  # fmt: skip
    assert row.newest_snapshot == "20261120T010000Z" and row.repository_bytes == 1234


def test_an_offsite_prune_never_touches_the_source_catalog(session, sent):  # noqa: F811
    s = _offsite(session, _setup(session))
    _snapshot(session, s, "20261119T010000Z")
    row = _ready_row(session, s, sent)
    run = replicas.queue_offsite(session, row, "prune")
    session.commit()
    _finish(session, run, pruned=["20261119T010000Z"])
    live = session.query(models.BackupSnapshot).filter_by(name="20261119T010000Z").one()
    assert live.gone_at is None


def test_held_snapshots_are_never_pruned_where_restate_cannot_keep_them(
    session, sent
):  # noqa: F811
    s = _offsite(session, _setup(session))
    row = _ready_row(session, s, sent)
    row.abilities = json.dumps([])
    session.add(models.BackupLegalHold(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id,
        snapshot="20261119T010000Z", owner="Matter 1", reason="Proof",
        placed_by="a@example.com", placed_at=datetime(2026, 11, 20),
    ))  # fmt: skip
    session.commit()
    payload = replicas.configuration(session, row, s.policy, s.holder)
    assert "prune" not in payload["jobs"]
    run = replicas.queue_offsite(session, row, "protect")
    session.commit()
    _finish(session, run)
    assert _runs(session, "off_prune") == []
    assert _runs(session, "off_du")


def test_a_copy_the_source_forgot_resends_its_job_files(session, sent):  # noqa: F811
    s = _offsite(session, _setup(session))
    _snapshot(session, s, "20261119T010000Z")
    _ready_row(session, s, sent)
    version = s.policy.config_version
    copy = _runs(session, "copy")[-1]
    results.record_command_result(
        session,
        {"command_id": copy.command_id, "success": False, "error": "not_configured"},
    )
    assert s.policy.config_version == version + 1
    assert copy.status == "failed"


def test_a_new_token_keeps_the_old_one_until_the_grant_has_it(
    session, sent
):  # noqa: F811
    s = _offsite(session, _setup(session))
    row = _ready_row(session, s, sent)
    assert replicas.store_tokens(
        session, s.policy, {"copy_tokens": {str(row.id): NEW_TOKEN}}
    )
    assert row.token_sha256_old == TOKEN
    payload = replicas.configuration(session, row, s.policy, s.holder)
    assert payload["target"]["proxy"]["grants"][0]["token_sha256"] == [NEW_TOKEN, TOKEN]
    replicas.configure_pending(session)
    session.commit()
    _ack(session, _runs(session, "off_configure")[-1])
    assert row.token_sha256_old is None


def test_the_offsite_target_keeps_copy_grants_among_its_clients(
    session, sent
):  # noqa: F811
    s = _offsite(session, _setup(session))
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    row = replicas.rows(session, s.policy)[0]
    assert proxy.target_clients(session, s.holder) == [
        f"offsite-{row.id}",
        f"replica-{row.id}",
    ]


def test_stopping_the_copy_drops_its_row(session, sent):  # noqa: F811
    s = _offsite(session, _setup(session))
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    s.target.replica_target_id = None
    session.commit()
    assert replicas.ensure(session, s.policy, s.target, s.host) is None
    session.commit()
    assert replicas.rows(session, s.policy) == []


def test_the_host_view_shows_how_far_behind(session, sent):  # noqa: F811
    s = _offsite(session, _setup(session))
    _snapshot(session, s, "20261120T010000Z")
    row = _ready_row(session, s, sent)
    row.newest_at = datetime(2026, 11, 20, 1, 0)
    row.newest_snapshot = "20261120T010000Z"
    row.snapshots = json.dumps(["20261120T010000Z"])
    view = replicas.view(session, s.policy, datetime(2026, 11, 21, 7, 0))
    assert view[0]["target"] == "Offsite"
    assert view[0]["lag_hours"] == 30.0 and view[0]["behind"] == 0


def test_every_stored_offsite_action_fits_the_run_column():
    """backup_run.action is 16 characters; PostgreSQL refused a longer one
    and rolled back the whole result with it (lab, 2026-11-20)."""
    width = models.BackupRun.__table__.c.action.type.length
    stored = [replicas.COPY] + [
        replicas.run_action(a) for a in replicas._ACTIONS + (jobs.CONFIGURE,)
    ]
    assert all(len(name) <= width for name in stored), stored


def test_the_offsite_hosts_audit_of_a_copy_is_taken_quietly(
    session, sent
):  # noqa: F811
    s = _offsite(session, _setup(session))
    row = _ready_row(session, s, sent)
    payload = {"policy_id": str(row.id), "storage_audit": []}
    assert results.record_storage_audit(session, s.nas2.id, payload) is True
    assert results.record_storage_audit(session, s.nas.id, payload) is False


def test_the_storage_hosts_own_backup_is_copied_off_site_too(
    session, sent
):  # noqa: F811
    """The server's own backup lives on its storage host (``self``, 24.13):
    the one a lost site needs most."""
    s = _offsite(session, _setup(session))
    s.policy.host_id = s.nas.id  # the storage host backs itself up
    session.commit()
    jobs.queue_configure(session, s.policy, s.target, s.nas, jobs.SELF_ROLE)
    session.commit()
    row = replicas.rows(session, s.policy)[0]
    assert sent[-1][2]["replicas"][0]["id"] == str(row.id)
    _ack(session, _runs(session, jobs.CONFIGURE)[-1],
         {"copy_tokens": {str(row.id): TOKEN}, "storage_abilities": ["replica_copy"]})  # fmt: skip
    assert row.token_sha256 == TOKEN


# --- restoring from the copy (the site-loss drill) -------------------------

READ = "d" * 64


def _readable_row(session, s, sent):  # noqa: F811
    """A copy the host may read: its agent reads off-site copies, its read
    token is in the off-site grant, and the copy holds one snapshot."""
    row = _ready_row(session, s, sent)
    s.policy.host_abilities = json.dumps(["list", "offsite_read"])
    row.snapshots = json.dumps(["20261119T010000Z"])
    session.commit()
    assert replicas.store_read_tokens(
        session, s.policy, {"offsite_tokens": {str(row.id): READ}}
    )
    replicas.configure_pending(session)
    session.commit()
    _ack(session, _runs(session, "off_configure")[-1])
    return row


def test_the_host_is_told_where_its_copies_are_and_reads_with_its_own_token(
    session, sent  # noqa: F811
):
    s = _offsite(session, _setup(session))
    row = _ready_row(session, s, sent)
    assert replicas.host_block(session, s.policy) == {}  # an older agent
    s.policy.host_abilities = json.dumps(["offsite_read"])
    assert replicas.host_block(session, s.policy) == {"offsite": [{
        "id": str(row.id),
        "url": f"https://backup.dc2.lab:8443/v1/offsite-{row.id}",
        "pin_sha256": "c" * 64,
    }]}  # fmt: skip
    replicas.store_read_tokens(
        session, s.policy, {"offsite_tokens": {str(row.id): READ}}
    )
    grants = replicas.configuration(session, row, s.policy, s.holder)["target"][
        "proxy"
    ]["grants"]
    assert {"client": f"offsite-{row.id}", "token_sha256": [READ],
            "operations": ["read"]} in grants  # fmt: skip
    assert f"offsite-{row.id}" in proxy.target_clients(session, s.holder)


def test_a_new_copy_retells_the_backed_up_host(session, sent):  # noqa: F811
    """The host's configure may be built before the storage side's makes
    the copy row; the host must still learn the copy, or it never makes a
    read token for it (lab, 2026-11-21)."""
    s = _offsite(session, _setup(session))
    version = s.policy.config_version
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    assert len(replicas.rows(session, s.policy)) == 1
    assert s.policy.config_version == version + 1  # the host is sent it again
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    assert s.policy.config_version == version + 1  # once
    s.target.replica_target_id = None
    session.commit()
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    assert replicas.rows(session, s.policy) == []
    assert s.policy.config_version == version + 2  # and when it goes


def test_a_restore_from_the_copy_never_asks_this_sites_storage(
    session, sent, monkeypatch
):  # noqa: F811
    from backend.api import backups as api  # pylint: disable=import-outside-toplevel
    from backend.services import (
        backup_reach as reach,
    )  # pylint: disable=import-outside-toplevel
    from tests.test_backups_api import (
        RESTORER,
    )  # pylint: disable=import-outside-toplevel

    s = _offsite(session, _setup(session))
    _readable_row(session, s, sent)
    monkeypatch.setattr(reach, "blocked", lambda _db, _host: True)  # the site is down
    body = api.RestoreBody(snapshot="20261119T010000Z", offsite=True, dry_run=True)
    data = api.backup_restore(str(s.host.id), body, session, RESTORER)
    params = sent[-1][2]
    row = replicas.rows(session, s.policy)[0]
    assert params["offsite"] == str(row.id) and params["snapshot"] == "20261119T010000Z"
    assert data["action"] == "restore"


@pytest.mark.asyncio
async def test_an_offsite_restore_is_refused_with_its_reason(
    session, sent
):  # noqa: F811
    from backend.api import backups as api  # pylint: disable=import-outside-toplevel
    from tests.test_backups_api import (
        RESTORER,
        _status,
    )  # pylint: disable=import-outside-toplevel

    s = _offsite(session, _setup(session))
    row = _ready_row(session, s, sent)

    def ask(name="20261119T010000Z"):
        body = api.RestoreBody(snapshot=name, offsite=True, dry_run=True)
        return _status(
            lambda: api.backup_restore(str(s.host.id), body, session, RESTORER)
        )

    assert await ask() == 409  # the agent cannot read copies yet
    s.policy.host_abilities = json.dumps(["offsite_read"])
    session.commit()
    assert await ask() == 409  # no read token in the grant yet
    _readable_row(session, s, sent)
    assert await ask("20261101T010000Z") == 409  # not in the copy
    assert row.read_token_sha256 == READ


def test_browsing_the_copy_goes_through_its_proxy(
    session, sent, monkeypatch
):  # noqa: F811
    from backend.api import (
        backups_browse as browse,
    )  # pylint: disable=import-outside-toplevel
    from backend.services import (
        backup_reach as reach,
    )  # pylint: disable=import-outside-toplevel
    from tests.test_backups_api import (
        RESTORER,
    )  # pylint: disable=import-outside-toplevel

    s = _offsite(session, _setup(session))
    row = _readable_row(session, s, sent)
    monkeypatch.setattr(reach, "blocked", lambda _db, _host: True)
    body = browse.BrowseBody(snapshot="20261119T010000Z", path="/etc", offsite=True)
    browse.browse_snapshot(str(s.host.id), body, session, RESTORER)
    assert sent[-1][2]["offsite"] == str(row.id) and sent[-1][2]["path"] == "/etc"
