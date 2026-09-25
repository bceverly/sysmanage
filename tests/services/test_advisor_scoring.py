# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Advisor scoring over stored outcomes -- Phase 21.2 S3.

The engine's withholding rules are tested in its own repo. What is tested
here is the part the server owns: every approved host reaches the engine --
including one with no rows yet -- and nothing else does.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import advisor_scoring as scoring

NOW = datetime.now(timezone.utc).replace(tzinfo=None)


class Engine:
    """Records what it was given; grades like the real one's shape."""

    def __init__(self):
        self.hosts = []

    def score_host(self, results):
        self.hosts.append(results)
        fired = [r["risk"] for r in results if r["outcome"] == "fires"]
        gaps = any(r["outcome"] == "not_assessable" for r in results)
        if fired:
            return {"score": max(fired) * 4, "level": "X", "complete": not gaps}
        if results and not gaps:
            return {"score": 0, "level": "NONE", "complete": True}
        return {"score": None, "level": "UNKNOWN", "complete": False}

    def score_fleet(self, host_scores):
        assessed = [h["score"] for h in host_scores if h["score"] is not None]
        return {
            "total_hosts": len(host_scores),
            "assessed_hosts": len(assessed),
            "unknown_hosts": len(host_scores) - len(assessed),
        }


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _host(db, approval="approved"):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"h-{uuid.uuid4().hex[:6]}",
        active=True,
        approval_status=approval,
    )
    db.add(host)
    db.commit()
    return host


def _result(db, host, key, outcome, risk=None, at=NOW):
    db.add(
        models.AdvisorResult(
            host_id=host.id,
            rule_source="shared",
            rule_key=key,
            outcome=outcome,
            risk=risk,
            evaluated_at=at,
        )
    )
    db.commit()


def test_a_hosts_rows_reach_the_engine_with_their_risk(db):
    host = _host(db)
    _result(db, host, "A", "fires", risk=20, at=NOW - timedelta(hours=2))
    _result(db, host, "B", "does_not_fire", at=NOW)
    engine = Engine()
    score = scoring.host_score(engine, db, host.id)
    assert score["score"] == 80 and score["evaluated_at"] == NOW
    assert sorted(r["outcome"] for r in engine.hosts[0]) == ["does_not_fire", "fires"]


def test_a_never_evaluated_host_is_unknown_with_no_evaluation_time(db):
    host = _host(db)
    score = scoring.host_score(Engine(), db, host.id)
    assert score["level"] == "UNKNOWN" and score["evaluated_at"] is None


def test_a_host_with_no_rows_still_counts_in_the_fleet(db):
    """Dropping it would make the fleet look fully assessed."""
    scored, blank = _host(db), _host(db)
    _result(db, scored, "A", "does_not_fire")
    fleet = scoring.fleet_score(Engine(), db)
    assert fleet == {"total_hosts": 2, "assessed_hosts": 1, "unknown_hosts": 1}
    assert blank  # present in the fleet only as an unknown


def test_unapproved_hosts_are_not_part_of_the_fleet(db):
    _host(db, approval="pending")
    _result(db, _host(db), "A", "does_not_fire")
    assert scoring.fleet_score(Engine(), db)["total_hosts"] == 1


def test_the_fleet_can_be_limited_to_some_hosts(db):
    one, two = _host(db), _host(db)
    _result(db, one, "A", "fires", risk=4)
    _result(db, two, "A", "does_not_fire")
    engine = Engine()
    fleet = scoring.fleet_score(engine, db, host_ids=[one.id])
    assert fleet["total_hosts"] == 1 and engine.hosts[0][0]["risk"] == 4


def test_an_empty_fleet(db):
    assert scoring.fleet_score(Engine(), db)["total_hosts"] == 0
