# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Multiple backup targets (ROADMAP 27.3, Enterprise backup_ops_engine).

One target is the default and takes new hosts; a policy may name another.
Each target's hosts back up to its own storage host, at its own
concurrency.  After a lapse every target keeps working, but nothing is added
and no host moves (Bryan, 2026-11-20)."""

# pylint: disable=redefined-outer-name,unused-argument

import uuid
from datetime import datetime

import pytest

from backend.api import backups as api
from backend.api import backups_setup as setup_api
from backend.api import backups_tag_policies as tag_api
from backend.api import backups_targets as targets_api
from backend.persistence import models
from backend.services import backup_breakglass as breakglass
from backend.services import backup_jobs as jobs
from backend.services import backup_reach as reach
from backend.services import backup_tag_policies as tag_policies
from backend.services import backup_targets as targets
from backend.services import backup_tick as tick
from backend.services import backup_views as views
from tests.services.test_backup_results import _host, _setup
from tests.test_backups_api import (  # noqa: F401  pylint: disable=unused-import
    MANAGER,
    _status,
    sent,
)

NOW = datetime(2026, 11, 20, 3, 0)


@pytest.fixture
def ops_engine(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("backup_ops_engine")
    monkeypatch.setattr(targets, "engine", lambda: eng)
    return eng


@pytest.fixture
def unlicensed(monkeypatch):
    monkeypatch.setattr(targets, "engine", lambda: None)


def _second(session, name="offsite", fqdn="nas2.lab", **extra):
    """A second target on its own storage host (its rows, no API)."""
    nas = _host(session, fqdn=fqdn)
    target = models.BackupTarget(
        id=uuid.uuid4(), name=name, host_mount_point="/mnt/offsite",
        storage_host_id=nas.id, storage_path="/srv/offsite",
        max_concurrent=1, seal_mode="none",
        created_at=datetime(2026, 11, 1), updated_at=datetime(2026, 11, 1),
        **extra,
    )  # fmt: skip
    session.add(target)
    session.commit()
    return target, nas


def _body(**extra):
    values = {"name": "offsite", "host_mount_point": "/mnt/offsite", **extra}
    return targets_api.TargetBody(**values)


def _snapshot(session, policy, name="20261119T010000Z"):
    session.add(
        models.BackupSnapshot(
            id=uuid.uuid4(), policy_id=policy.id, host_id=policy.host_id, name=name,
            created_at=datetime(2026, 11, 19), seen_at=datetime(2026, 11, 19),
        )  # fmt: skip
    )
    session.commit()


# --- the targets themselves ------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_target_needs_the_engine_and_is_not_the_default(
    session, ops_engine
):
    s = _setup(session)
    assert jobs.default_target(session).id == s.target.id  # oldest, unmarked
    made = targets_api.create_target(_body(), session, MANAGER)
    assert made["is_default"] is False
    assert [t["name"] for t in targets_api.list_targets(session)] == ["nas", "offsite"]
    # It must not collide with another target (the engine decides).
    clash = _body(name="NAS", host_mount_point="/mnt/x")
    assert (
        await _status(lambda: targets_api.create_target(clash, session, MANAGER)) == 409
    )
    same_mount = _body(name="third", host_mount_point="/mnt/backups")
    assert (
        await _status(lambda: targets_api.create_target(same_mount, session, MANAGER))
        == 409
    )


@pytest.mark.asyncio
async def test_without_the_engine_the_first_target_is_all(session, unlicensed):
    made = targets_api.create_target(_body(name="first"), session, MANAGER)
    assert made["is_default"] is True
    assert (
        await _status(lambda: targets_api.create_target(_body(), session, MANAGER))
        == 402
    )


@pytest.mark.asyncio
async def test_the_default_moves_and_is_frozen_after_a_lapse(
    session, ops_engine, monkeypatch
):
    s = _setup(session)
    second, _nas = _second(session)
    targets_api.set_default_target(str(second.id), session, MANAGER)
    assert jobs.default_target(session).id == second.id
    assert session.get(models.BackupTarget, s.target.id).is_default is False
    monkeypatch.setattr(targets, "engine", lambda: None)
    assert (
        await _status(
            lambda: targets_api.set_default_target(str(s.target.id), session, MANAGER)
        )
        == 402
    )


@pytest.mark.asyncio
async def test_what_cannot_be_deleted(session, ops_engine):
    s = _setup(session)
    second, _nas = _second(session)
    targets.make_default(session, s.target)
    session.commit()
    # In use by a host policy; the default while another remains.
    in_use = str(s.target.id)
    assert (
        await _status(lambda: targets_api.delete_target(in_use, session, MANAGER))
        == 409
    )
    tag = models.Tag(id=uuid.uuid4(), name="web", created_at=NOW, updated_at=NOW)
    session.add(tag)
    session.add(
        models.BackupTagPolicy(
            id=uuid.uuid4(), name="web", tag_id=tag.id, priority=1, enabled=True,
            settings="{}", target_id=second.id, created_at=NOW, updated_at=NOW,
        )  # fmt: skip
    )
    session.commit()
    assert (
        await _status(
            lambda: targets_api.delete_target(str(second.id), session, MANAGER)
        )
        == 409  # a tag policy sends its hosts there
    )


def test_an_unused_target_that_is_not_the_default_is_deleted(session, ops_engine):
    _setup(session)
    second, _nas = _second(session)
    assert targets_api.delete_target(str(second.id), session, MANAGER) == {
        "deleted": True
    }


# --- host policies ----------------------------------------------------------


def _policy_body(**extra):
    return api.PolicyBody(**extra)


@pytest.mark.asyncio
async def test_a_new_host_goes_to_the_default_unless_it_names_another(
    session, sent, ops_engine, monkeypatch
):
    s = _setup(session)
    second, _nas = _second(session)
    plain = _host(session, fqdn="plain.lab")
    api.save_policy(session, MANAGER, plain, _policy_body())
    assert jobs.host_target(session, plain).id == s.target.id
    named = _host(session, fqdn="named.lab")
    api.save_policy(session, MANAGER, named, _policy_body(target_id=str(second.id)))
    assert jobs.host_target(session, named).id == second.id
    # Without the engine a new host can still take the default, never another.
    monkeypatch.setattr(targets, "engine", lambda: None)
    late = _host(session, fqdn="late.lab")
    body = _policy_body(target_id=str(second.id))
    assert await _status(lambda: api.save_policy(session, MANAGER, late, body)) == 402
    api.save_policy(session, MANAGER, late, _policy_body())
    assert jobs.host_target(session, late).id == s.target.id


@pytest.mark.asyncio
async def test_after_a_lapse_a_host_keeps_its_target_and_cannot_move(
    session, sent, ops_engine, monkeypatch
):
    s = _setup(session)
    second, _nas = _second(session)
    s.policy.target_id = second.id
    session.commit()
    monkeypatch.setattr(targets, "engine", lambda: None)
    api.save_policy(session, MANAGER, s.host, _policy_body(keep_last=9))
    assert jobs.host_target(session, s.host).id == second.id  # still there
    back = _policy_body(target_id=str(s.target.id))
    assert await _status(lambda: api.save_policy(session, MANAGER, s.host, back)) == 402


@pytest.mark.asyncio
async def test_a_host_with_backups_moves_only_to_a_proxy_target(
    session, sent, ops_engine
):
    s = _setup(session)
    second, _nas = _second(session)
    api.save_policy(session, MANAGER, s.host, _policy_body(target_id=str(second.id)))
    assert jobs.host_target(session, s.host).id == second.id
    _snapshot(session, s.policy)
    back = _policy_body(target_id=str(s.target.id))
    assert await _status(lambda: api.save_policy(session, MANAGER, s.host, back)) == 409


def test_bulk_setup_puts_the_hosts_on_the_target_asked_for(session, sent, ops_engine):
    _setup(session)
    second, _nas = _second(session)
    host = _host(session, fqdn="bulk.lab")
    body = setup_api.BulkSetupBody(host_ids=[str(host.id)], target_id=str(second.id))
    assert setup_api.bulk_backup_setup(body, session, MANAGER)["created"] == 1
    assert jobs.host_target(session, host).id == second.id


# --- the tick --------------------------------------------------------------


def test_each_target_configures_its_hosts_against_its_own_storage_host(session, sent):
    s = _setup(session, storage_acked=0)
    second, nas2 = _second(session)
    other = _host(session, fqdn="other.lab")
    session.add(
        models.BackupPolicy(
            id=uuid.uuid4(), host_id=other.id, target_id=second.id, enabled=True,
            interval_hours=24, keep_last=14, check_interval_days=7, quiesce=False,
            config_version=1, host_acked_version=0, storage_acked_version=0,
            created_at=NOW, updated_at=NOW,
        )  # fmt: skip
    )
    s.policy.host_acked_version = 0
    session.commit()
    tick.reconcile(session, NOW)
    storage_jobs = {
        (host_id, params["policy_id"])
        for host_id, command, params in sent
        if command == "backup_configure" and params.get("role") == "storage"
    }
    other_policy = jobs.target_of(session, s.policy)  # the first target
    assert other_policy.id == s.target.id
    assert (str(s.nas.id), str(s.policy.id)) in storage_jobs
    assert any(host_id == str(nas2.id) for host_id, _p in storage_jobs)
    assert not any(
        host_id == str(s.nas.id) and pid != str(s.policy.id)
        for host_id, pid in storage_jobs
    )


def test_each_target_has_its_own_concurrency(session, sent):
    s = _setup(session)
    second, _nas = _second(session)  # max_concurrent 1
    hosts = [_host(session, fqdn=f"h{i}.lab") for i in range(2)]
    for host in hosts:
        session.add(
            models.BackupPolicy(
                id=uuid.uuid4(), host_id=host.id, target_id=second.id, enabled=True,
                interval_hours=24, keep_last=14, check_interval_days=7,
                quiesce=False, config_version=1, host_acked_version=1,
                storage_acked_version=1, capture_requested_at=NOW,
                created_at=NOW, updated_at=NOW,
            )  # fmt: skip
        )
    s.policy.capture_requested_at = NOW
    session.commit()
    assert tick.start_requested(session) == 2  # one on each target


# --- what reads a host's target --------------------------------------------


def test_a_host_checks_reach_to_its_own_targets_storage(session, ops_engine):
    s = _setup(session)
    second, nas2 = _second(session)
    nas2.ipv4 = "192.0.2.20"
    s.nas.ipv4 = "192.0.2.10"
    other = _host(session, fqdn="other.lab")
    session.add(
        models.BackupPolicy(
            id=uuid.uuid4(), host_id=other.id, target_id=second.id, enabled=True,
            interval_hours=24, keep_last=14, check_interval_days=7, quiesce=False,
            config_version=1, host_acked_version=1, storage_acked_version=1,
            created_at=NOW, updated_at=NOW,
        )  # fmt: skip
    )
    session.commit()
    assert reach.storage_address(session, s.host)["host_id"] == s.nas.id
    assert reach.storage_address(session, other)["host_id"] == nas2.id


def test_the_overview_lists_every_target_and_counts_each_problem(session):
    _setup(session)
    second, _nas = _second(session)
    second.storage_host_id = None  # no storage host: a problem
    session.commit()
    data = views.overview(session)
    assert [t["name"] for t in data["targets"]] == ["nas", "offsite"]
    assert data["target"]["name"] == "nas" and data["targets"][0]["is_default"]
    problems = views.target_problems(data)
    assert problems == sum(1 for t in data["targets"] if t["problem"]) >= 1


def test_a_tag_policy_sends_new_hosts_to_its_target_only_while_licensed(
    session, ops_engine, monkeypatch
):
    s = _setup(session)
    second, _nas = _second(session)
    row = SimpleTag(target_id=second.id)
    assert tag_policies.tag_target(session, row, s.target).id == second.id
    monkeypatch.setattr(targets, "engine", lambda: None)
    assert tag_policies.tag_target(session, row, s.target).id == s.target.id


class SimpleTag:  # pylint: disable=too-few-public-methods
    def __init__(self, target_id):
        self.target_id = target_id


@pytest.mark.asyncio
async def test_naming_another_target_on_a_tag_policy_is_enterprise(session, unlicensed):
    s = _setup(session)
    second, _nas = _second(session)
    body = SimpleBody(target_id=str(second.id))
    assert await _status(lambda: tag_api._target_id(session, body)) == 402
    assert tag_api._target_id(session, SimpleBody(target_id=str(s.target.id))) == (
        s.target.id
    )
    assert tag_api._target_id(session, SimpleBody(target_id=None)) is None


class SimpleBody:  # pylint: disable=too-few-public-methods
    def __init__(self, target_id):
        self.target_id = target_id


def test_a_key_export_names_each_hosts_own_target_and_signer(session):
    s = _setup(session)
    second, _nas = _second(
        session, sign_public_key="-----BEGIN PGP PUBLIC KEY BLOCK-----\nB",
        sign_fingerprint="BBBB",
    )  # fmt: skip
    s.target.sign_public_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nA"
    s.target.sign_fingerprint = "AAAA"
    other = _host(session, fqdn="other.lab")
    policy = models.BackupPolicy(
        id=uuid.uuid4(), host_id=other.id, target_id=second.id, enabled=True,
        interval_hours=24, keep_last=14, check_interval_days=7, quiesce=False,
        config_version=1, host_acked_version=1, storage_acked_version=1,
        repository_dir="other-1", created_at=NOW, updated_at=NOW,
    )  # fmt: skip
    session.add(policy)
    s.policy.repository_dir = "web-1"
    session.commit()
    entries = breakglass.gather_export(
        session,
        [(s.host, s.policy), (other, policy)],
        s.target,
        vault=object(),
        keys=lambda *_a: [],
    )
    by_host = {e["host"]: e for e in entries}
    assert by_host["other.lab"]["storage_repository"] == "/srv/offsite/other-1"
    assert by_host["other.lab"]["target"] == "offsite"
    bundle = breakglass.build_bundle(
        entries, "now", "me", "drill", "KEY", breakglass.signer_of(s.target)
    )
    import io  # pylint: disable=import-outside-toplevel
    import json  # pylint: disable=import-outside-toplevel
    import tarfile  # pylint: disable=import-outside-toplevel

    with tarfile.open(fileobj=io.BytesIO(bundle)) as archive:
        names = archive.getnames()
        manifest = json.loads(archive.extractfile("manifest.json").read())
    assert breakglass.SIGNING_FILE in names
    assert "keys/signing-BBBB.pub.asc" in names
    files = {h["host"]: h["signing_file"] for h in manifest["hosts"]}
    assert files["other.lab"] == "keys/signing-BBBB.pub.asc"
    assert files[s.host.fqdn] == breakglass.SIGNING_FILE


# --- off-site copies (27.3) -----------------------------------------------


def _proxy_second(session):
    return _second(
        session, transport="proxy", proxy_host="backup.dc2.lab", proxy_port=8443
    )


def test_a_target_copies_off_site_to_a_proxy_target_on_another_host(
    session, sent, ops_engine
):
    s = _setup(session)
    second, _nas = _proxy_second(session)
    version = s.policy.config_version
    data = targets_api.set_replica_target(
        str(s.target.id),
        targets_api.ReplicaBody(replica_target_id=str(second.id)),
        session,
        MANAGER,
    )
    assert data["replica_target"] == "offsite"
    assert s.policy.config_version == version + 1  # its storage host is told
    assert views.target_dict(second, session)["copies_from"] == ["nas"]


@pytest.mark.asyncio
async def test_off_site_copies_are_refused_where_they_could_be_lost(
    session, ops_engine
):
    s = _setup(session)
    nfs, _nas = _second(session)
    body = targets_api.ReplicaBody(replica_target_id=str(nfs.id))
    assert (
        await _status(
            lambda: targets_api.set_replica_target(
                str(s.target.id), body, session, MANAGER
            )
        )
        == 409
    )  # not behind restate-proxy
    body = targets_api.ReplicaBody(replica_target_id=str(s.target.id))
    assert (
        await _status(
            lambda: targets_api.set_replica_target(
                str(s.target.id), body, session, MANAGER
            )
        )
        == 409
    )  # itself


@pytest.mark.asyncio
async def test_off_site_copies_need_the_license_to_change(session, unlicensed):
    s = _setup(session)
    second, _nas = _proxy_second(session)
    body = targets_api.ReplicaBody(replica_target_id=str(second.id))
    assert (
        await _status(
            lambda: targets_api.set_replica_target(
                str(s.target.id), body, session, MANAGER
            )
        )
        == 402
    )


@pytest.mark.asyncio
async def test_a_target_holding_copies_cannot_be_deleted(session, sent, ops_engine):
    s = _setup(session)
    second, _nas = _proxy_second(session)
    targets_api.set_replica_target(
        str(s.target.id),
        targets_api.ReplicaBody(replica_target_id=str(second.id)),
        session,
        MANAGER,
    )
    assert (
        await _status(
            lambda: targets_api.delete_target(str(second.id), session, MANAGER)
        )
        == 409
    )
    targets_api.set_replica_target(
        str(s.target.id), targets_api.ReplicaBody(), session, MANAGER
    )
    assert targets_api.delete_target(str(second.id), session, MANAGER) == {
        "deleted": True
    }
