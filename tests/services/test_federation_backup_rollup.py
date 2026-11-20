# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backup status per federated site (Phase 27.1).

Each site server owns its backup target and all backup data; the
coordinator stores only a status snapshot.  These tests cover both halves:
the site's snapshot (built from the Backups overview, throttled, status
only) and the coordinator's record / read / prune.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import (
    FederationBackupRollup,
    FederationSite,
)
from backend.services import backup_views
from backend.services import federation_rollup_service as rollup_svc
from backend.services import federation_site_backup_rollup as site_backup


def _naive_utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def session():
    engine = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


@pytest.fixture
def site(session):
    row = FederationSite(
        id=uuid.uuid4(),
        name="site-a",
        url="https://s.example",
        status="enrolled",
        sync_interval_seconds=300,
        created_at=_naive_utcnow(),
        updated_at=_naive_utcnow(),
    )
    session.add(row)
    session.commit()
    return row


# --- the site's snapshot ---------------------------------------------------


def _row(fqdn, status, good=None, verify=None, size=0, policy=True):
    return {
        "host_id": str(uuid.uuid4()),
        "fqdn": fqdn,
        "status": status,
        "policy": (
            {"repository_bytes": size, "storage_path": "/srv/backups/" + fqdn}
            if policy
            else None
        ),
        "last_good_capture": (
            {"finished_at": good, "snapshot": "20261119T000000Z"} if good else None
        ),
        "verification": {"state": verify} if verify else None,
    }


@pytest.fixture
def overview(monkeypatch):
    data = {
        "target": {"name": "nas", "storage_path": "/srv/backups/restate"},
        "hosts": [
            _row("a.lan", "ok", "2026-11-19T01:00:00", "verified", 100),
            _row("b.lan", "overdue", "2026-11-10T01:00:00", "unverified", 200),
            _row("c.lan", "failed", None, None, 0),
            _row("d.lan", "ok", "2026-11-18T01:00:00", "verified", 50),
            _row("e.lan", "no_policy", policy=False),
        ],
        "counts": {},
        "server": {"warn": False},
    }
    for row in data["hosts"]:
        data["counts"][row["status"]] = data["counts"].get(row["status"], 0) + 1
    monkeypatch.setattr(backup_views, "overview", lambda _db: data)
    monkeypatch.setattr(backup_views, "target_problem", lambda _d: False)
    return data


def test_snapshot_counts_the_covered_hosts(overview):
    body = site_backup.collect_backup_rollup(None)
    assert body["configured"] is True
    assert body["hosts_with_policy"] == 4  # e.lan has no policy
    assert body["status_counts"] == {"ok": 2, "overdue": 1, "failed": 1}
    assert body["verification_counts"] == {"verified": 2, "unverified": 1}
    assert body["never_backed_up"] == 1
    assert body["repository_bytes"] == 350
    assert body["oldest_last_good_at"] == "2026-11-10T01:00:00"
    assert body["attention_count"] == 2


def test_snapshot_names_attention_hosts_never_backed_up_first(overview):
    hosts = site_backup.collect_backup_rollup(None)["attention_hosts"]
    assert [h["fqdn"] for h in hosts] == ["c.lan", "b.lan"]
    assert hosts[0]["last_good_at"] is None
    assert set(hosts[0]) == {"host_id", "fqdn", "status", "last_good_at"}


def test_snapshot_carries_no_backup_data(overview):
    """Paths, snapshot names and the target's details stay on the site."""
    text = json.dumps(site_backup.collect_backup_rollup(None))
    assert "/srv/backups" not in text
    assert "20261119T000000Z" not in text
    assert "nas" not in text


def test_snapshot_caps_the_named_hosts(monkeypatch):
    rows = [_row(f"h{i}.lan", "failed") for i in range(25)]
    data = {"target": None, "hosts": rows, "counts": {"failed": 25}}
    monkeypatch.setattr(backup_views, "overview", lambda _db: data)
    monkeypatch.setattr(backup_views, "target_problem", lambda _d: False)
    body = site_backup.collect_backup_rollup(None)
    assert body["configured"] is False
    assert len(body["attention_hosts"]) == site_backup.MAX_ATTENTION_HOSTS
    assert body["attention_count"] == 25


class _Bind:
    url = "sqlite:///site.db"


class _Session:
    def get_bind(self):
        return _Bind()


@pytest.fixture
def queue(monkeypatch, overview):
    sent = []
    monkeypatch.setattr(site_backup.coord_svc, "is_enrolled", lambda _s: True)
    monkeypatch.setattr(
        site_backup.sync_svc,
        "enqueue",
        lambda _s, **kw: sent.append(kw) or kw,
    )
    monkeypatch.setattr(site_backup, "_last_taken", {})
    return sent


def test_enqueue_is_throttled_per_database(queue, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(site_backup.time, "monotonic", lambda: clock[0])
    assert site_backup.enqueue_backup_rollup(_Session()) is not None
    clock[0] += 10
    assert site_backup.enqueue_backup_rollup(_Session()) is None
    clock[0] += site_backup.REFRESH_SECONDS
    assert site_backup.enqueue_backup_rollup(_Session()) is not None
    assert len(queue) == 2
    assert queue[0]["payload_type"] == "backup_rollup"
    assert queue[0]["dedup_key"] == "backup_rollup:self"


def test_enqueue_force_skips_the_wait(queue):
    site_backup.enqueue_backup_rollup(_Session())
    assert site_backup.enqueue_backup_rollup(_Session(), force=True) is not None
    assert len(queue) == 2


def test_enqueue_nothing_when_not_enrolled(queue, monkeypatch):
    monkeypatch.setattr(site_backup.coord_svc, "is_enrolled", lambda _s: False)
    assert site_backup.enqueue_backup_rollup(_Session()) is None
    assert not queue


# --- the coordinator's record / read / prune -------------------------------


def _body(**over):
    body = {
        "configured": True,
        "target_problem": False,
        "hosts_with_policy": 4,
        "attention_count": 2,
        "never_backed_up": 1,
        "repository_bytes": 350,
        "oldest_last_good_at": "2026-11-10T01:00:00+00:00",
        "status_counts": {"ok": 2, "overdue": 1, "failed": 1},
        "verification_counts": {"verified": 2},
        "attention_hosts": [
            {
                "host_id": "h1",
                "fqdn": "c.lan",
                "status": "failed",
                "last_good_at": None,
                "storage_path": "/srv/should-not-be-kept",
            }
        ],
    }
    body.update(over)
    return body


def test_record_and_read_round_trip(session, site):
    rollup_svc.record_backup_rollup_snapshot(session, site_id=site.id, body=_body())
    session.commit()
    view = rollup_svc.backup_rollup_dict(
        rollup_svc.get_latest_backup_rollup(session, site.id)
    )
    assert view["configured"] is True
    assert view["hosts_with_policy"] == 4
    assert view["repository_bytes"] == 350
    assert view["oldest_last_good_at"] == "2026-11-10T01:00:00"  # naive UTC
    assert view["status_counts"] == {"ok": 2, "overdue": 1, "failed": 1}
    assert view["attention_hosts"] == [
        {"host_id": "h1", "fqdn": "c.lan", "status": "failed", "last_good_at": None}
    ]


def test_record_keeps_only_status_fields_of_named_hosts(session, site):
    row = rollup_svc.record_backup_rollup_snapshot(
        session, site_id=site.id, body=_body()
    )
    assert "should-not-be-kept" not in (row.attention_hosts_json or "")


def test_record_caps_named_hosts(session, site):
    hosts = [
        {"host_id": str(i), "fqdn": f"h{i}", "status": "failed"} for i in range(30)
    ]
    row = rollup_svc.record_backup_rollup_snapshot(
        session, site_id=site.id, body=_body(attention_hosts=hosts)
    )
    assert len(json.loads(row.attention_hosts_json)) == 10


@pytest.mark.parametrize(
    "over",
    [
        {"hosts_with_policy": -1},
        {"repository_bytes": "lots"},
        {"attention_hosts": "c.lan"},
        {"status_counts": ["ok"]},
        {"oldest_last_good_at": "yesterday"},
    ],
)
def test_record_rejects_a_malformed_body(session, site, over):
    with pytest.raises(ValueError):
        rollup_svc.record_backup_rollup_snapshot(
            session, site_id=site.id, body=_body(**over)
        )


def test_record_unknown_site_is_refused(session):
    with pytest.raises(LookupError):
        rollup_svc.record_backup_rollup_snapshot(
            session, site_id=uuid.uuid4(), body=_body()
        )


def test_latest_is_the_newest(session, site):
    base = _naive_utcnow()
    for i in range(3):
        rollup_svc.record_backup_rollup_snapshot(
            session,
            site_id=site.id,
            body=_body(hosts_with_policy=i),
            snapshot_at=base + timedelta(seconds=i),
        )
    session.commit()
    assert rollup_svc.get_latest_backup_rollup(session, site.id).hosts_with_policy == 2
    assert rollup_svc.backup_rollup_dict(None) is None


def test_prune_covers_the_backup_series(session, site):
    base = _naive_utcnow()
    for i in range(6):
        rollup_svc.record_backup_rollup_snapshot(
            session,
            site_id=site.id,
            body=_body(),
            snapshot_at=base + timedelta(seconds=i),
        )
    session.commit()
    counts = rollup_svc.prune_rollups(session, keep_per_series=2)
    session.commit()
    assert counts["backup"] == 4
    assert session.query(FederationBackupRollup).count() == 2


def test_readiness_counts_go_up_where_the_site_has_the_engine(overview, monkeypatch):
    from backend.services import (
        backup_readiness,
    )  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(backup_readiness, "engine", lambda: None)
    assert site_backup.collect_backup_rollup(None)["readiness_counts"] is None
    counts = {"ready": 3, "unproven": 1, "rpo_breached": 0, "never_backed_up": 0}
    monkeypatch.setattr(backup_readiness, "engine", object)
    monkeypatch.setattr(
        backup_readiness, "fleet", lambda _s, _e, _n: {"counts": counts}
    )
    assert site_backup.collect_backup_rollup(None)["readiness_counts"] == counts


def test_a_readiness_failure_never_fails_the_snapshot(overview, monkeypatch):
    from backend.services import (
        backup_readiness,
    )  # pylint: disable=import-outside-toplevel

    def boom(*_a):
        raise RuntimeError("engine fault")

    monkeypatch.setattr(backup_readiness, "engine", object)
    monkeypatch.setattr(backup_readiness, "fleet", boom)
    assert site_backup.collect_backup_rollup(None)["readiness_counts"] is None


def test_the_controller_keeps_readiness_counts(session, site):
    counts = {"ready": 3, "unproven": 1}
    rollup_svc.record_backup_rollup_snapshot(
        session, site_id=site.id, body=_body(readiness_counts=counts)
    )
    rollup_svc.record_backup_rollup_snapshot(
        session, site_id=site.id, body=_body(),
        snapshot_at=_naive_utcnow() - timedelta(days=1),
    )  # fmt: skip
    session.commit()
    view = rollup_svc.backup_rollup_dict(
        rollup_svc.get_latest_backup_rollup(session, site.id)
    )
    assert view["readiness_counts"] == counts
