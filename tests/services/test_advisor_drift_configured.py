# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Drift evidence for a host no configuration profile reaches.

Drift is measured by a successful check-mode run.  A host nothing was ever
assigned to can never have one, so reporting its drift rules as
not_assessable withheld its advisor score forever (production, 2026-10-16).
The gatherer now marks such a host ``configured: False`` and the engine
reports those rules as not applicable.  A host WITH an assignment but no
check is still a blind spot, and a checked host is measured either way.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import advisor_evidence as ev

NOW = datetime(2026, 10, 16, 12, 0, 0)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _host(db, **kw):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"h-{uuid.uuid4().hex[:6]}",
        active=True,
        approval_status="approved",
        **kw,
    )
    db.add(host)
    db.commit()
    return host


def _profile(db):
    profile = models.ConfigProfile(
        id=uuid.uuid4(),
        name=f"p-{uuid.uuid4().hex[:6]}",
        engine="ansible-core",
        content="- hosts: all\n",
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(profile)
    db.commit()
    return profile


def _assign(db, enabled=True, **target):
    db.add(
        models.ConfigProfileAssignment(
            id=uuid.uuid4(),
            profile_id=_profile(db).id,
            enabled=enabled,
            created_at=NOW,
            **target,
        )
    )
    db.commit()


def _drift(db, host):
    evidence, _ = ev.gather(db, host, {}, {"drift"})
    return evidence["domains"]["drift"]


def test_a_host_nothing_reaches_is_marked_unconfigured(db):
    assert _drift(db, _host(db)) == {"at": None, "configured": False}


def test_a_directly_assigned_host_is_a_real_gap(db):
    host = _host(db)
    _assign(db, host_id=host.id)
    assert _drift(db, host) == {"at": None}


def test_an_assignment_through_a_tag_counts(db):
    host = _host(db)
    tag = models.Tag(id=uuid.uuid4(), name="web", created_at=NOW, updated_at=NOW)
    db.add(tag)
    db.add(
        models.HostTag(id=uuid.uuid4(), host_id=host.id, tag_id=tag.id, created_at=NOW)
    )
    db.commit()
    _assign(db, tag_id=tag.id)
    assert _drift(db, host) == {"at": None}


def test_a_disabled_assignment_does_not_count(db):
    host = _host(db)
    _assign(db, enabled=False, host_id=host.id)
    assert _drift(db, host)["configured"] is False


def test_another_hosts_assignment_does_not_count(db):
    host, other = _host(db), _host(db)
    _assign(db, host_id=other.id)
    assert _drift(db, host)["configured"] is False


def test_a_checked_host_is_measured_without_an_assignment(db):
    host = _host(db)
    db.add(
        models.ConfigProfileRun(
            host_id=host.id,
            check_mode=True,
            success=True,
            completed_at=NOW,
            created_at=NOW,
        )
    )
    db.commit()
    assert _drift(db, host) == {"at": NOW}


def test_the_bulk_chunk_agrees_with_the_per_host_answer(db):
    """The tick gathers through a chunk (Phase 22.3): same answer, without
    a query per host."""
    from backend.services import advisor_evidence_bulk as bulk_ev

    tag = models.Tag(id=uuid.uuid4(), name="db", created_at=NOW, updated_at=NOW)
    db.add(tag)
    hosts = [_host(db) for _ in range(4)]
    db.add(
        models.HostTag(
            id=uuid.uuid4(), host_id=hosts[1].id, tag_id=tag.id, created_at=NOW
        )
    )
    db.commit()
    _assign(db, host_id=hosts[0].id)
    _assign(db, tag_id=tag.id)
    _assign(db, enabled=False, host_id=hosts[2].id)
    chunk = bulk_ev.Chunk(db, hosts, {"drift"})
    for host in hosts:
        evidence, _ = ev.gather(db, host, {}, {"drift"}, bulk=chunk)
        assert evidence["domains"]["drift"] == _drift(db, host)
    assert [chunk.is_drift_configured(h) for h in hosts] == [True, True, False, False]
