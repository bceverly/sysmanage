# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Remediation proposals -- Phase 21.2 S5.

The properties: nothing is applied without an approval; an approval goes
through the EXISTING apply path; an operator is asked once per fix, not once
per tick; a proposal is withdrawn when the problem is gone, but not merely
because the host could not be assessed.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import advisor_proposals as ap

NOW = datetime.now(timezone.utc).replace(tzinfo=None)
ENTRY = {
    "source": "tenant",
    "key": "AVAIL-001",
    "shared_rule_id": None,
    "rule_id": None,
}
GEN = {
    "kind": "generate",
    "engine": "ansible-core",
    "content": "- hosts: all\n",
    "packages": ["openssl"],
    "skipped": 0,
}


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _host(db):
    host = models.Host(
        id=uuid.uuid4(), fqdn="h1", active=True, approval_status="approved"
    )
    db.add(host)
    db.commit()
    return host


def _sync(db, host, outcome="fires", fix=GEN):
    summary = {}
    ap.sync(db, host.id, ENTRY, {"outcome": outcome, "fix": fix}, summary)
    db.commit()
    return summary


def _all(db):
    return (
        db.query(models.AdvisorProposal)
        .order_by(models.AdvisorProposal.created_at)
        .all()
    )


class TestSync:
    def test_a_firing_rule_with_a_fix_is_proposed_not_applied(self, db):
        host = _host(db)
        with patch.object(ap.remediation, "apply_remediation") as applied:
            assert _sync(db, host)["proposals_opened"] == 1
        applied.assert_not_called()
        (row,) = _all(db)
        assert row.status == ap.PROPOSED and row.packages == ["openssl"]

    def test_the_same_fix_is_not_proposed_twice(self, db):
        host = _host(db)
        _sync(db, host)
        _sync(db, host)
        assert len(_all(db)) == 1

    def test_a_changed_fix_refreshes_the_open_proposal(self, db):
        host = _host(db)
        _sync(db, host)
        _sync(db, host, fix=dict(GEN, content="- hosts: all # v2\n", packages=["a"]))
        (row,) = _all(db)
        assert row.packages == ["a"]

    def test_a_rejected_fix_is_not_asked_again(self, db):
        """Once per fix -- not once per fifteen-minute tick."""
        host = _host(db)
        _sync(db, host)
        ap.reject(_all(db)[0], "op@example.com")
        db.commit()
        _sync(db, host)
        assert [r.status for r in _all(db)] == [ap.REJECTED]

    def test_a_different_fix_after_a_rejection_is_a_new_question(self, db):
        host = _host(db)
        _sync(db, host)
        ap.reject(_all(db)[0], "op@example.com")
        db.commit()
        _sync(db, host, fix=dict(GEN, content="- hosts: all # new package\n"))
        assert [r.status for r in _all(db)] == [ap.REJECTED, ap.PROPOSED]

    def test_withdrawn_when_the_problem_is_gone(self, db):
        host = _host(db)
        _sync(db, host)
        _sync(db, host, outcome="does_not_fire", fix=None)
        (row,) = _all(db)
        assert row.status == ap.WITHDRAWN and row.reason == ap.REASON_NO_LONGER_FIRES

    def test_not_withdrawn_merely_because_it_could_not_be_assessed(self, db):
        """Missing evidence says nothing about whether the problem went away."""
        host = _host(db)
        _sync(db, host)
        _sync(db, host, outcome="not_assessable", fix=None)
        assert _all(db)[0].status == ap.PROPOSED

    def test_a_removed_rule_withdraws_its_open_proposals(self, db):
        host = _host(db)
        _sync(db, host)
        ap.withdraw_for(db, "tenant", "AVAIL-001")
        assert _all(db)[0].reason == ap.REASON_RULE_REMOVED


class TestApproval:
    def test_a_generated_fix_becomes_a_real_profile_and_is_applied(self, db):
        host = _host(db)
        _sync(db, host)
        row = _all(db)[0]
        with patch.object(
            ap.remediation, "apply_remediation", return_value="cmd-1"
        ) as applied:
            ap.approve(db, row, "op@example.com")
        db.commit()
        profile = db.get(models.ConfigProfile, row.profile_id)
        assert profile.engine == "ansible-core" and profile.content == GEN["content"]
        assert applied.call_args.args[2] is profile
        assert (row.status, row.command_id, row.decided_by) == (
            ap.APPROVED,
            "cmd-1",
            "op@example.com",
        )

    def test_a_bound_fix_applies_the_named_profile(self, db):
        host = _host(db)
        db.add(
            models.ConfigProfile(
                id=uuid.uuid4(),
                name="patch-openssl",
                engine="ansible-core",
                content="- hosts: all\n",
                version=1,
                is_active=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        db.commit()
        _sync(db, host, fix={"kind": "profile", "profile": "patch-openssl"})
        row = _all(db)[0]
        with patch.object(
            ap.remediation, "apply_remediation", return_value="c"
        ) as applied:
            ap.approve(db, row, "op@example.com")
        assert applied.call_args.args[2].name == "patch-openssl"

    def test_a_missing_bound_profile_fails_with_a_reason(self, db):
        host = _host(db)
        _sync(db, host, fix={"kind": "profile", "profile": "gone"})
        row = _all(db)[0]
        with pytest.raises(ap.ProposalError) as err:
            ap.approve(db, row, "op@example.com")
        assert err.value.code == ap.REASON_PROFILE_MISSING
        assert row.status == ap.FAILED

    def test_a_host_that_cannot_take_the_command_fails_visibly(self, db):
        host = _host(db)
        _sync(db, host)
        row = _all(db)[0]
        with patch.object(
            ap.remediation, "apply_remediation", side_effect=RuntimeError("unsupported")
        ):
            with pytest.raises(ap.ProposalError):
                ap.approve(db, row, "op@example.com")
        assert (row.status, row.reason) == (ap.FAILED, ap.REASON_NOT_QUEUED)
        db.commit()
        # The generated profile went with the failed attempt -- no orphan.
        assert db.query(models.ConfigProfile).count() == 0

    def test_only_a_proposed_fix_can_be_decided(self, db):
        host = _host(db)
        _sync(db, host)
        row = _all(db)[0]
        ap.reject(row, "op@example.com")
        with pytest.raises(ap.ProposalError):
            ap.approve(db, row, "op@example.com")

    def test_the_run_it_produced_is_reported(self, db):
        host = _host(db)
        _sync(db, host)
        row = _all(db)[0]
        with patch.object(ap.remediation, "apply_remediation", return_value="cmd-9"):
            ap.approve(db, row, "op@example.com")
        assert ap.proposal_dict(db, row)["run"] is None  # queued, not yet run
        db.add(
            models.ConfigProfileRun(
                host_id=host.id,
                command_id="cmd-9",
                success=True,
                completed_at=NOW,
                created_at=NOW,
            )
        )
        db.commit()
        assert ap.proposal_dict(db, row)["run"]["success"] is True
