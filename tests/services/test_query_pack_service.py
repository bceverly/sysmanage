# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for ``query_pack_service`` -- Phase 21.1 S4.

The service owns the DATABASE and nothing else: every rule comes from the
licensed engine through the shim. So these tests are about persistence and
about the two places where a wrong shape would quietly produce a wrong answer:

  * a pack must be VALIDATED before it is stored, because a stored pack can be
    assigned and dispatched before anyone finds out, and its SQL is
    tenant-authored; and
  * "not covered" must survive being written to the database. A query that
    could not run gets a row saying so -- without it, the run's counts would be
    the only evidence the question was ever asked.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from backend.persistence import models
from backend.services import query_pack_service as svc


def q(name="ports", sql="SELECT port FROM listening_ports", **kw):
    row = {"name": name, "sql": sql, "required_tables": ["listening_ports"]}
    row.update(kw)
    return row


def _valid(_pack):
    return {"valid": True, "problems": []}


def _invalid(_pack):
    return {
        "valid": False,
        "problems": ["a query may only read; 'delete' is not allowed"],
    }


class TestPackStorage:
    def test_a_valid_pack_is_stored_with_its_queries(self, session):
        with patch.object(svc.shim, "validate_pack", _valid):
            pack, problems = svc.create_pack(session, "ports", [q()])
        assert problems == []
        assert pack.version == 1
        assert [x.name for x in pack.queries] == ["ports"]

    def test_an_invalid_pack_is_never_stored(self, session):
        """A stored pack can be assigned and dispatched before anyone looks at
        it, and the SQL in it came from a user."""
        with patch.object(svc.shim, "validate_pack", _invalid):
            pack, problems = svc.create_pack(session, "bad", [q(sql="DELETE FROM x")])
        assert pack is None and problems
        assert session.query(models.QueryPack).count() == 0

    def test_editing_the_queries_bumps_the_version(self, session):
        with patch.object(svc.shim, "validate_pack", _valid):
            pack, _ = svc.create_pack(session, "p", [q()])
            updated, _ = svc.update_pack(session, pack, queries=[q("other")])
        assert updated.version == 2
        assert [x.name for x in updated.queries] == ["other"]

    def test_editing_only_the_description_does_not_bump_the_version(self, session):
        """The version is what an assignment compares against to say 'this
        pack changed under you'. Bumping it for a typo fix cries wolf."""
        with patch.object(svc.shim, "validate_pack", _valid):
            pack, _ = svc.create_pack(session, "p", [q()])
            updated, _ = svc.update_pack(session, pack, description="clearer")
        assert updated.version == 1

    def test_a_rejected_edit_leaves_the_stored_pack_alone(self, session):
        with patch.object(svc.shim, "validate_pack", _valid):
            pack, _ = svc.create_pack(session, "p", [q()])
        with patch.object(svc.shim, "validate_pack", _invalid):
            updated, problems = svc.update_pack(session, pack, queries=[q("bad")])
        assert updated is None and problems
        assert [x.name for x in pack.queries] == ["ports"]
        assert pack.version == 1


class TestAssignments:
    def test_an_assignment_needs_exactly_one_pack(self, session):
        _, problems = svc.create_assignment(
            session,
            pack_id=uuid.uuid4(),
            shared_pack_id=uuid.uuid4(),
            host_id=uuid.uuid4(),
        )
        assert problems
        _, problems = svc.create_assignment(session, host_id=uuid.uuid4())
        assert problems

    def test_an_assignment_needs_exactly_one_target(self, session):
        """NOT a fleet-wide wildcard. A policy that applied everywhere because
        a field was left empty gets noticed only after it has run everywhere."""
        _, problems = svc.create_assignment(session, pack_id=uuid.uuid4())
        assert problems
        _, problems = svc.create_assignment(
            session, pack_id=uuid.uuid4(), host_id=uuid.uuid4(), tag_id=uuid.uuid4()
        )
        assert problems

    def test_a_well_formed_assignment_is_stored(self, session):
        assignment, problems = svc.create_assignment(
            session, pack_id=uuid.uuid4(), host_id=uuid.uuid4(), interval_minutes=30
        )
        assert problems == []
        assert assignment.interval_minutes == 30

    def test_an_interval_below_the_floor_is_refused(self, session):
        _, problems = svc.create_assignment(
            session, pack_id=uuid.uuid4(), host_id=uuid.uuid4(), interval_minutes=1
        )
        assert problems


class TestPackResolution:
    def test_a_disabled_tenant_pack_does_not_resolve(self, session):
        with patch.object(svc.shim, "validate_pack", _valid):
            pack, _ = svc.create_pack(session, "p", [q()], enabled=False)
        assert svc.resolve_pack(session, {"pack_id": pack.id}) is None

    def test_a_missing_curated_pack_resolves_to_none_not_an_empty_pack(self, session):
        """An empty pack would dispatch, run nothing, and come back a clean
        success -- reporting a host as measured against a pack that is gone."""
        with patch.object(svc, "get_shared_pack", return_value=None):
            resolved = svc.resolve_pack(
                session, {"shared_pack_id": uuid.uuid4(), "assignment_id": "a1"}
            )
        assert resolved is None


class TestResultRecording:
    def _run(self, session):
        host_id = uuid.uuid4()
        return models.QueryPackRun(
            id=uuid.uuid4(),
            host_id=host_id,
            pack_name="p",
            status=models.RUN_STATUS_PENDING,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    def test_rows_are_stored_one_per_result_row(self, session):
        """Every S6 consumer asks 'which hosts returned a row matching X',
        which is a query over rows, not a scan of documents."""
        run = self._run(session)
        session.add(run)
        session.flush()
        svc.record_results(
            session,
            run,
            {
                "contract_version": 1,
                "results": [
                    {
                        "name": "ports",
                        "status": "ok",
                        "rows": [{"port": 22}, {"port": 443}],
                    }
                ],
            },
        )
        rows = session.query(models.QueryPackResultRow).all()
        assert len(rows) == 2
        assert {r.columns["port"] for r in rows} == {22, 443}

    def test_a_not_covered_query_leaves_a_row_saying_so(self, session):
        """Without it the run's counts would be the only evidence the question
        was ever asked."""
        run = self._run(session)
        session.add(run)
        session.flush()
        svc.record_results(
            session,
            run,
            {
                "results": [
                    {
                        "name": "procs",
                        "status": "not_covered",
                        "reason": "insufficient_privilege",
                        "rows": [],
                    }
                ]
            },
        )
        row = session.query(models.QueryPackResultRow).one()
        assert row.status == "not_covered"
        assert row.reason == "insufficient_privilege"
        assert row.columns is None

    def test_a_run_with_an_uncovered_query_is_partial_not_success(self, session):
        """THE property. Success here would report a host compliant on a
        question nobody asked it."""
        run = self._run(session)
        session.add(run)
        session.flush()
        svc.record_results(
            session,
            run,
            {
                "results": [
                    {"name": "a", "status": "ok", "rows": [{"n": 1}]},
                    {"name": "b", "status": "not_covered", "reason": "wrong_platform"},
                ]
            },
        )
        assert run.status == models.RUN_STATUS_PARTIAL
        assert run.queries_not_covered == 1
        assert run.queries_ok == 1

    def test_the_agents_contract_version_is_recorded(self, session):
        """A fleet upgrades gradually; without this, comparing results across
        hosts silently compares different contracts."""
        run = self._run(session)
        session.add(run)
        session.flush()
        svc.record_results(
            session,
            run,
            {
                "contract_version": 1,
                "results": [{"name": "a", "status": "ok", "rows": [{"n": 1}]}],
            },
        )
        assert run.contract_version == 1

    def test_an_ok_query_returning_nothing_still_leaves_a_row(self, session):
        """'Measured, found none' is a real finding and must be recorded as
        one -- distinct from 'not measured', which is recorded differently."""
        run = self._run(session)
        session.add(run)
        session.flush()
        svc.record_results(
            session, run, {"results": [{"name": "a", "status": "ok", "rows": []}]}
        )
        row = session.query(models.QueryPackResultRow).one()
        assert row.status == "ok"
        assert row.columns is None
        assert run.status == models.RUN_STATUS_SUCCESS
