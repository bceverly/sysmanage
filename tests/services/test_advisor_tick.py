# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The advisor evaluation tick and its evidence gatherer -- Phase 21.2 S2.

The licensed engine decides outcomes and is tested in its own repo; what is
tested here is everything around it that could quietly turn "could not
evaluate" into "fine": evidence read from the wrong clock, an error stored as
nothing, a result filed under the wrong rule, curated results pruned because
the catalog was unreadable.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import advisor_evidence as ev
from backend.services import advisor_tick as tick

NOW = datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
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


def _rule(key, scope="host", domains=("updates",), **extra):
    rule = {
        "id": key,
        "version": 1,
        "contract": 1,
        "title": key,
        "lens": "availability",
        "scope": scope,
        "requires": {"domains": list(domains)},
        "when": "SELECT package_name FROM sm_pending_update",
        "impact": 3,
        "likelihood": 3,
        "remediation": "-",
    }
    rule.update(extra)
    return rule


class FakeEngine:
    """Outcomes from evidence the same way the engine's contract does it:
    missing evidence -> not_assessable; otherwise fires iff rows exist."""

    def evaluate_host(self, rules, evidence, tables, now=None):
        out = []
        for rule in rules:
            if rule.get("scope", "host") != "host":
                continue
            domain = rule["requires"]["domains"][0]
            if (evidence["domains"].get(domain) or {}).get("at") is None:
                out.append(
                    {
                        "rule_id": rule["id"],
                        "rule_version": 1,
                        "lens": rule["lens"],
                        "outcome": "not_assessable",
                        "gaps": [{"evidence": domain, "reason": "missing"}],
                    }
                )
                continue
            rows = tables.get("sm_pending_update") or []
            out.append(
                {
                    "rule_id": rule["id"],
                    "rule_version": 1,
                    "lens": rule["lens"],
                    "outcome": "fires" if rows else "does_not_fire",
                    "impact": 3,
                    "likelihood": 3,
                    "risk": 9 if rows else None,
                    "match_count": len(rows),
                    "matches": rows,
                }
            )
        return out

    def evaluate_fleet(self, rule, hosts, now=None):
        return {
            h["host_id"]: {
                "rule_id": rule["id"],
                "outcome": "not_assessable",
                "gaps": [{"evidence": "peer", "reason": "insufficient_peers"}],
            }
            for h in hosts
        }


def _tick(make_session, shared_rules=()):
    """One tick over one database, with the given curated rules."""

    def _dbs():
        yield ("bootstrap", None, make_session())

    shared = (
        None
        if shared_rules is None
        else [
            {
                "source": "shared",
                "key": r["id"],
                "shared_rule_id": uuid.uuid4(),
                "rule_id": None,
                "rule": r,
                "pack": "test-pack",
                "pack_default": True,
            }
            for r in shared_rules
        ]
    )
    with patch.object(
        tick.module_loader, "get_module", return_value=FakeEngine()
    ), patch.object(tick, "iter_host_databases", _dbs), patch.object(
        tick, "load_shared_rules", return_value=shared
    ):
        return tick.run_one_tick()


def _results(make_session):
    with make_session() as db:
        return {
            (r.rule_source, r.rule_key, str(r.host_id)): r
            for r in db.query(models.AdvisorResult).all()
        }


# ------------------------------------------------------------------- tick


class TestTick:
    def test_unlicensed_is_a_no_op(self):
        with patch.object(tick.module_loader, "get_module", return_value=None):
            assert tick.run_one_tick()["results"] == 0

    def test_a_host_that_never_reported_gets_a_not_assessable_row(self, make_session):
        """The phase's property: never checked is a VISIBLE row, not absence."""
        with make_session() as db:
            host = _host(db)
        _tick(make_session, [_rule("AVAIL-001")])
        row = _results(make_session)[("shared", "AVAIL-001", str(host.id))]
        assert row.outcome == "not_assessable"
        assert row.gaps == [{"evidence": "updates", "reason": "missing"}]

    def test_measured_evidence_decides_and_the_row_is_replaced(self, make_session):
        with make_session() as db:
            host = _host(db, updates_updated_at=NOW)
        _tick(make_session, [_rule("AVAIL-001")])
        assert _results(make_session)[
            ("shared", "AVAIL-001", str(host.id))
        ].outcome == ("does_not_fire")
        with make_session() as db:
            db.add(
                models.PackageUpdate(
                    host_id=host.id,
                    package_name="openssl",
                    current_version="1",
                    available_version="2",
                    package_manager="apt",
                    update_type="security",
                    status="available",
                    discovered_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            db.commit()
        _tick(make_session, [_rule("AVAIL-001")])
        results = _results(make_session)
        assert len(results) == 1
        row = results[("shared", "AVAIL-001", str(host.id))]
        assert row.outcome == "fires" and row.match_count == 1
        assert (row.impact, row.likelihood, row.risk) == (3, 3, 9)

    def test_a_tenant_rule_sharing_a_curated_key_keeps_its_own_outcome(
        self, make_session
    ):
        """Results are matched by position: by key, one would overwrite the other."""
        with make_session() as db:
            host = _host(db, updates_updated_at=NOW, reboot_required_updated_at=None)
            db.add(
                models.AdvisorRule(
                    rule_key="SEC-001",
                    lens="security",
                    title="t",
                    definition=_rule("SEC-001", domains=("reboot",)),
                )
            )
            db.commit()
        _tick(make_session, [_rule("SEC-001")])
        results = _results(make_session)
        assert results[("shared", "SEC-001", str(host.id))].outcome == "does_not_fire"
        assert results[("tenant", "SEC-001", str(host.id))].outcome == "not_assessable"

    def test_a_tenant_that_switched_the_pack_off_gets_no_curated_results(
        self, make_session
    ):
        """S6: per-tenant choice over one shared copy of the pack."""
        with make_session() as db:
            host = _host(db)
            db.add(models.AdvisorPackSetting(pack_slug="test-pack", enabled=False))
            db.commit()
        _tick(make_session, [_rule("A")])
        assert _results(make_session) == {}
        assert host

    def test_a_withdrawn_rule_takes_its_results_with_it(self, make_session):
        with make_session() as db:
            host = _host(db)
        _tick(make_session, [_rule("A"), _rule("B")])
        _tick(make_session, [_rule("A")])
        assert set(_results(make_session)) == {("shared", "A", str(host.id))}

    def test_an_unreadable_catalog_does_not_prune_curated_results(self, make_session):
        with make_session() as db:
            host = _host(db)
        _tick(make_session, [_rule("A")])
        _tick(make_session, None)  # load_shared_rules() failed this pass
        assert ("shared", "A", str(host.id)) in _results(make_session)

    def test_a_host_that_cannot_be_gathered_keeps_its_previous_results(
        self, make_session
    ):
        with make_session() as db:
            host = _host(db)
        _tick(make_session, [_rule("A")])
        before = _results(make_session)[("shared", "A", str(host.id))].evaluated_at
        with patch.object(tick.ev, "gather", side_effect=RuntimeError("db gone")):
            summary = _tick(make_session, [_rule("A")])
        assert summary["host_errors"] == 1
        assert (
            _results(make_session)[("shared", "A", str(host.id))].evaluated_at == before
        )

    def test_a_down_host_is_still_evaluated(self, make_session):
        """Skipping it would leave its last outcome standing as if current."""
        with make_session() as db:
            host = _host(db)
            host.active = False
            db.commit()
        _tick(make_session, [_rule("A")])
        assert ("shared", "A", str(host.id)) in _results(make_session)

    def test_an_unapproved_host_is_not_evaluated(self, make_session):
        with make_session() as db:
            host = _host(db)
            host.approval_status = "pending"
            db.commit()
        _tick(make_session, [_rule("A")])
        assert _results(make_session) == {}

    def test_fleet_rules_are_stored_per_host(self, make_session):
        with make_session() as db:
            host = _host(db, platform="Linux", platform_release="24.04")
        _tick(make_session, [_rule("F", scope="fleet", peer_group="os_release")])
        assert _results(make_session)[("shared", "F", str(host.id))].outcome == (
            "not_assessable"
        )

    def test_a_host_deleted_takes_its_results(self, make_session):
        with make_session() as db:
            host = _host(db)
        _tick(make_session, [_rule("A")])
        with make_session() as db:
            db.execute(
                models.AdvisorResult.__table__.delete().where(
                    models.AdvisorResult.host_id == host.id
                )
            )
            db.delete(db.get(models.Host, host.id))
            db.commit()
        assert _results(make_session) == {}


# --------------------------------------------------------------- evidence


def _fact_run(db, host, table, status="ok", rows=None, at=NOW):
    run = models.QueryPackRun(id=uuid.uuid4(), host_id=host.id, status="success")
    db.add(run)
    db.flush()
    payloads = rows if rows else [None]
    for payload in payloads:
        db.add(
            models.QueryPackResultRow(
                id=uuid.uuid4(),
                run_id=run.id,
                query_name=ev.FACT_QUERY_PREFIX + table,
                status=status,
                columns=payload,
                collected_at=at,
            )
        )
    db.commit()


@contextmanager
def _serves(columns=("path", "blocks")):
    with patch.object(ev.host_facts, "missing_columns", return_value=None) as mc:
        yield mc


class TestEvidence:
    def test_each_domain_reads_its_own_clock(self, make_session):
        with make_session() as db:
            host = _host(
                db,
                updates_updated_at=NOW - timedelta(days=3),
                software_updated_at=NOW,
                reboot_required_updated_at=None,
            )
            evidence, _tables = ev.gather(
                db, host, {}, {"updates", "packages", "reboot"}
            )
        assert evidence["domains"]["updates"]["at"] == NOW - timedelta(days=3)
        assert evidence["domains"]["packages"]["at"] == NOW
        assert evidence["domains"]["reboot"]["at"] is None

    def test_an_unknown_domain_is_left_for_the_engine_to_call_unavailable(
        self, make_session
    ):
        with make_session() as db:
            host = _host(db)
            evidence, _ = ev.gather(db, host, {}, {"metric_history"})
        assert "metric_history" not in evidence["domains"]

    def test_drift_is_measured_by_a_successful_check_run_not_by_findings(
        self, make_session
    ):
        with make_session() as db:
            host = _host(db)
            db.add(
                models.ConfigProfileRun(
                    host_id=host.id,
                    check_mode=False,
                    success=True,
                    completed_at=NOW,
                    created_at=NOW,
                )
            )
            db.commit()
            evidence, _ = ev.gather(db, host, {}, {"drift"})
        assert evidence["domains"]["drift"]["at"] is None

    def test_uncollected_facts_have_no_collection_time(self, make_session):
        with make_session() as db, _serves():
            host = _host(db)
            evidence, tables = ev.gather(db, host, {"mounts": {"path"}}, set())
        assert evidence["facts"]["mounts"] == {"gap": None, "collected_at": None}
        assert "mounts" not in tables

    def test_collected_facts_bring_their_rows_and_time(self, make_session):
        with make_session() as db, _serves():
            host = _host(db)
            _fact_run(db, host, "mounts", rows=[{"path": "/"}, {"path": "/home"}])
            evidence, tables = ev.gather(db, host, {"mounts": {"path"}}, set())
        assert evidence["facts"]["mounts"]["collected_at"] == NOW
        assert sorted(r["path"] for r in tables["mounts"]) == ["/", "/home"]

    def test_an_empty_answer_is_a_collection_with_no_rows(self, make_session):
        with make_session() as db, _serves():
            host = _host(db)
            _fact_run(db, host, "mounts", rows=None)
            evidence, tables = ev.gather(db, host, {"mounts": {"path"}}, set())
        assert evidence["facts"]["mounts"]["collected_at"] == NOW
        assert "mounts" not in tables

    def test_an_errored_answer_is_not_a_collection(self, make_session):
        with make_session() as db, _serves():
            host = _host(db)
            _fact_run(db, host, "mounts", status="error")
            evidence, _ = ev.gather(db, host, {"mounts": {"path"}}, set())
        assert evidence["facts"]["mounts"]["collected_at"] is None

    def test_rows_missing_a_needed_column_are_not_a_collection(self, make_session):
        """Collected before a rule read ``type``: NULL for every row would
        silently not match, so it is ``not_collected`` until re-collected."""
        with make_session() as db, _serves():
            host = _host(db)
            _fact_run(db, host, "mounts", rows=[{"path": "/"}])
            evidence, tables = ev.gather(db, host, {"mounts": {"path", "type"}}, set())
        assert evidence["facts"]["mounts"]["collected_at"] is None
        assert "mounts" not in tables

    def test_a_coverage_gap_is_passed_through_and_rows_are_not_read(self, make_session):
        gap = {
            "table": "mounts",
            "state": "served",
            "reason": "columns_not_populated",
            "columns": ["blocks"],
        }
        with make_session() as db, patch.object(
            ev.host_facts, "missing_columns", return_value=gap
        ):
            host = _host(db)
            _fact_run(db, host, "mounts", rows=[{"path": "/"}])
            evidence, tables = ev.gather(db, host, {"mounts": {"blocks"}}, set())
        assert evidence["facts"]["mounts"] == {"gap": gap, "collected_at": None}
        assert "mounts" not in tables

    def test_required_collects_columns_and_domains_across_rules(self):
        rules = [
            {"requires": {"facts": {"mounts": ["path"]}, "domains": ["vuln"]}},
            {"requires": {"facts": {"mounts": ["blocks"]}, "domains": ["updates"]}},
            {"requires": {"facts": ["not-a-dict"]}},
        ]
        tables, domains = ev.required(rules)
        assert tables == {"mounts": {"path", "blocks"}}
        assert domains == {"vuln", "updates"}

    @pytest.mark.parametrize(
        "group,expected",
        [
            ("os_release", "Ubuntu 24.04"),
            ("site", None),
            ("tag", "t1,t2"),
            ("package_manager", None),
        ],
    )
    def test_peer_values(self, group, expected):
        class H:  # pylint: disable=too-few-public-methods
            platform, platform_release, site_id = "Ubuntu", "24.04", None

        assert ev.peer_value(H(), group, ["t2", "t1"]) == expected
