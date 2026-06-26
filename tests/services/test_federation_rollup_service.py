"""
Tests for the Phase 12.1.D federation rollup ingestion service.

Covers:
  * Host-directory upsert (insert path, update path, site-move path).
  * Append-only host/compliance/vulnerability snapshot rows with
    validation of count + percent constraints.
  * Latest-snapshot lookups return the freshest row per (site, baseline).
  * Dashboard rollup returns a coherent (host, [compliance], vuln) tuple.
  * Removed sites cannot ingest rollups.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import json
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.services import federation_rollup_service as rsvc
from backend.services import federation_site_service as ssvc
from tests.federation_crypto import quick_enroll

FEDERATION_TABLE_NAMES = [
    "federation_sites",
    "federation_host_directory",
    "federation_host_rollup",
    "federation_compliance_rollup",
    "federation_vulnerability_rollup",
    "federation_policies",
    "federation_policy_assignments",
    "federation_dispatched_commands",
    "federation_audit_log",
    "federation_site_sync_event",
    "federation_coordinator",
    "federation_sync_queue",
    "federation_received_policies",
    "federation_received_commands",
]


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in FEDERATION_TABLE_NAMES]
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


@pytest.fixture
def enrolled_site(session):
    """A site that's already finished enrollment — most rollup tests
    just want a parent row to point at."""
    site = quick_enroll(session, name="Cleveland", url="https://a.x")
    session.commit()
    return site


# ---------------------------------------------------------------------
# upsert_host_directory_entry
# ---------------------------------------------------------------------


class TestUpsertHostDirectory:
    def test_insert_path_creates_row(self, session, enrolled_site):
        import uuid

        host_id = uuid.uuid4()
        entry = rsvc.upsert_host_directory_entry(
            session,
            site_id=enrolled_site.id,
            host_id=host_id,
            fqdn="web1.cle.example.com",
            ipv4="10.0.0.10",
            os_family="ubuntu",
            status="up",
        )
        session.commit()
        assert entry.host_id == host_id
        assert entry.site_id == enrolled_site.id
        assert entry.fqdn == "web1.cle.example.com"
        assert entry.ipv4 == "10.0.0.10"
        assert entry.mtime is not None

    def test_update_path_overwrites_fields(self, session, enrolled_site):
        import uuid

        host_id = uuid.uuid4()
        rsvc.upsert_host_directory_entry(
            session,
            site_id=enrolled_site.id,
            host_id=host_id,
            fqdn="web1.cle.example.com",
            os_version="22.04",
            status="up",
        )
        session.commit()

        rsvc.upsert_host_directory_entry(
            session,
            site_id=enrolled_site.id,
            host_id=host_id,
            fqdn="web1.cle.example.com",  # unchanged
            os_version="24.04",  # upgraded
            status="down",  # went offline
        )
        session.commit()

        entry = rsvc.get_host_directory_entry(session, host_id)
        assert entry.os_version == "24.04"
        assert entry.status == "down"

    def test_site_move_updates_site_id(self, session, enrolled_site):
        """If an agent re-registers under a different coordinator-site
        binding, the directory row's site_id flips to the new owner."""
        import uuid

        # Second site.
        other = quick_enroll(session, name="Pittsburgh", url="https://b.x")
        session.commit()

        host_id = uuid.uuid4()
        rsvc.upsert_host_directory_entry(
            session,
            site_id=enrolled_site.id,
            host_id=host_id,
            fqdn="moves.example.com",
        )
        session.commit()

        rsvc.upsert_host_directory_entry(
            session,
            site_id=other.id,
            host_id=host_id,
            fqdn="moves.example.com",
        )
        session.commit()

        entry = rsvc.get_host_directory_entry(session, host_id)
        assert entry.site_id == other.id

    def test_unknown_field_raises(self, session, enrolled_site):
        import uuid

        with pytest.raises(ValueError):
            rsvc.upsert_host_directory_entry(
                session,
                site_id=enrolled_site.id,
                host_id=uuid.uuid4(),
                fqdn="x",
                hostname="not a column",  # not in whitelist
            )

    def test_missing_fqdn_raises(self, session, enrolled_site):
        import uuid

        with pytest.raises(ValueError):
            rsvc.upsert_host_directory_entry(
                session,
                site_id=enrolled_site.id,
                host_id=uuid.uuid4(),
                fqdn="   ",
            )

    def test_removed_site_rejects(self, session, enrolled_site):
        import uuid

        ssvc.remove_site(session, enrolled_site.id)
        session.commit()
        with pytest.raises(rsvc.UnknownSiteError):
            rsvc.upsert_host_directory_entry(
                session,
                site_id=enrolled_site.id,
                host_id=uuid.uuid4(),
                fqdn="x.y.z",
            )

    def test_explicit_mtime_preserved(self, session, enrolled_site):
        """Site replays a buffered delta with an old timestamp — the
        coordinator's mtime should match what the site sent so dedup
        replay logic stays correct."""
        import uuid

        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        rsvc.upsert_host_directory_entry(
            session,
            site_id=enrolled_site.id,
            host_id=uuid.uuid4(),
            fqdn="x.y.z",
            mtime=old,
        )
        session.commit()
        entry = (
            session.query(rsvc.FederationHostDirectory).filter_by(fqdn="x.y.z").first()
        )
        assert entry.mtime == old


class TestDeleteHostDirectoryEntry:
    def test_returns_true_when_deleted(self, session, enrolled_site):
        import uuid

        host_id = uuid.uuid4()
        rsvc.upsert_host_directory_entry(
            session,
            site_id=enrolled_site.id,
            host_id=host_id,
            fqdn="gone.example.com",
        )
        session.commit()
        assert rsvc.delete_host_directory_entry(session, host_id) is True
        session.commit()
        assert rsvc.get_host_directory_entry(session, host_id) is None

    def test_returns_false_when_not_present(self, session):
        import uuid

        assert rsvc.delete_host_directory_entry(session, uuid.uuid4()) is False


# ---------------------------------------------------------------------
# record_host_rollup_snapshot
# ---------------------------------------------------------------------


class TestHostRollupSnapshot:
    def test_append_with_breakdowns(self, session, enrolled_site):
        row = rsvc.record_host_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            host_count=12,
            active_count=10,
            os_breakdown={"ubuntu": 8, "debian": 4},
            status_breakdown={"up": 10, "down": 2},
        )
        session.commit()
        assert row.host_count == 12
        assert row.active_count == 10
        assert json.loads(row.os_breakdown_json) == {"ubuntu": 8, "debian": 4}
        assert json.loads(row.status_breakdown_json) == {"up": 10, "down": 2}

    def test_updates_site_host_count_by_default(self, session, enrolled_site):
        rsvc.record_host_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            host_count=42,
            active_count=40,
        )
        session.commit()
        assert enrolled_site.host_count == 42
        # ``last_sync_*`` columns are bumped via record_sync.
        assert enrolled_site.last_sync_at is not None
        assert enrolled_site.last_sync_status == "success"

    def test_update_site_host_count_disabled(self, session, enrolled_site):
        prior_count = enrolled_site.host_count
        rsvc.record_host_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            host_count=99,
            active_count=99,
            update_site_host_count=False,
        )
        session.commit()
        assert enrolled_site.host_count == prior_count

    def test_negative_count_raises(self, session, enrolled_site):
        with pytest.raises(ValueError):
            rsvc.record_host_rollup_snapshot(
                session,
                site_id=enrolled_site.id,
                host_count=-1,
                active_count=0,
            )

    def test_active_gt_total_raises(self, session, enrolled_site):
        with pytest.raises(ValueError):
            rsvc.record_host_rollup_snapshot(
                session,
                site_id=enrolled_site.id,
                host_count=5,
                active_count=10,
            )

    def test_removed_site_rejects(self, session, enrolled_site):
        ssvc.remove_site(session, enrolled_site.id)
        session.commit()
        with pytest.raises(rsvc.UnknownSiteError):
            rsvc.record_host_rollup_snapshot(
                session,
                site_id=enrolled_site.id,
                host_count=1,
                active_count=1,
            )


# ---------------------------------------------------------------------
# record_compliance_rollup_snapshot
# ---------------------------------------------------------------------


class TestComplianceRollupSnapshot:
    def test_happy_path(self, session, enrolled_site):
        row = rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            baseline="cis",
            score_percent=92.5,
            hosts_in_scope=10,
            hosts_compliant=9,
            hosts_noncompliant=1,
        )
        session.commit()
        assert row.baseline == "cis"
        assert row.score_percent == 92.5

    def test_score_out_of_range_raises(self, session, enrolled_site):
        with pytest.raises(ValueError):
            rsvc.record_compliance_rollup_snapshot(
                session,
                site_id=enrolled_site.id,
                baseline="cis",
                score_percent=150.0,
                hosts_in_scope=10,
                hosts_compliant=10,
                hosts_noncompliant=0,
            )

    def test_compliant_plus_noncompliant_too_large_raises(self, session, enrolled_site):
        with pytest.raises(ValueError):
            rsvc.record_compliance_rollup_snapshot(
                session,
                site_id=enrolled_site.id,
                baseline="cis",
                score_percent=80.0,
                hosts_in_scope=5,
                hosts_compliant=4,
                hosts_noncompliant=4,
            )

    def test_blank_baseline_raises(self, session, enrolled_site):
        with pytest.raises(ValueError):
            rsvc.record_compliance_rollup_snapshot(
                session,
                site_id=enrolled_site.id,
                baseline="   ",
                score_percent=80.0,
                hosts_in_scope=5,
                hosts_compliant=5,
                hosts_noncompliant=0,
            )

    def test_null_score_allowed(self, session, enrolled_site):
        """No hosts in scope -> NULL score is meaningful and accepted."""
        row = rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            baseline="cis",
            score_percent=None,
            hosts_in_scope=0,
            hosts_compliant=0,
            hosts_noncompliant=0,
        )
        session.commit()
        assert row.score_percent is None


# ---------------------------------------------------------------------
# record_vulnerability_rollup_snapshot
# ---------------------------------------------------------------------


class TestVulnerabilityRollupSnapshot:
    def test_happy_path_with_top_cves(self, session, enrolled_site):
        row = rsvc.record_vulnerability_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            critical_count=2,
            high_count=5,
            medium_count=10,
            low_count=4,
            affected_host_count=8,
            top_cve_ids=["CVE-2026-1", "CVE-2026-2"],
        )
        session.commit()
        assert row.critical_count == 2
        assert json.loads(row.top_cve_ids_json) == [
            "CVE-2026-1",
            "CVE-2026-2",
        ]

    def test_negative_counts_raise(self, session, enrolled_site):
        with pytest.raises(ValueError):
            rsvc.record_vulnerability_rollup_snapshot(
                session,
                site_id=enrolled_site.id,
                critical_count=-1,
            )

    def test_defaults_all_zero(self, session, enrolled_site):
        row = rsvc.record_vulnerability_rollup_snapshot(
            session, site_id=enrolled_site.id
        )
        session.commit()
        assert (
            row.critical_count
            == row.high_count
            == row.medium_count
            == row.low_count
            == 0
        )
        assert row.top_cve_ids_json is None


# ---------------------------------------------------------------------
# Latest-snapshot lookups
# ---------------------------------------------------------------------


class TestLatestLookups:
    def test_latest_host_rollup_picks_newest(self, session, enrolled_site):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rsvc.record_host_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            host_count=5,
            active_count=5,
            snapshot_at=now - timedelta(hours=1),
        )
        rsvc.record_host_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            host_count=8,
            active_count=7,
            snapshot_at=now,
        )
        session.commit()
        latest = rsvc.get_latest_host_rollup(session, enrolled_site.id)
        assert latest.host_count == 8

    def test_latest_host_rollup_returns_none(self, session, enrolled_site):
        assert rsvc.get_latest_host_rollup(session, enrolled_site.id) is None

    def test_latest_compliance_is_baseline_scoped(self, session, enrolled_site):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            baseline="cis",
            score_percent=80.0,
            hosts_in_scope=10,
            hosts_compliant=8,
            hosts_noncompliant=2,
            snapshot_at=now - timedelta(hours=2),
        )
        rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            baseline="cis",
            score_percent=90.0,
            hosts_in_scope=10,
            hosts_compliant=9,
            hosts_noncompliant=1,
            snapshot_at=now,
        )
        rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            baseline="stig",
            score_percent=70.0,
            hosts_in_scope=10,
            hosts_compliant=7,
            hosts_noncompliant=3,
            snapshot_at=now,
        )
        session.commit()
        latest_cis = rsvc.get_latest_compliance_rollup(
            session, enrolled_site.id, baseline="cis"
        )
        latest_stig = rsvc.get_latest_compliance_rollup(
            session, enrolled_site.id, baseline="stig"
        )
        assert latest_cis.score_percent == 90.0
        assert latest_stig.score_percent == 70.0


class TestDashboardRollup:
    def test_returns_latest_of_each(self, session, enrolled_site):
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        rsvc.record_host_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            host_count=5,
            active_count=5,
        )
        rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            baseline="cis",
            score_percent=80.0,
            hosts_in_scope=5,
            hosts_compliant=4,
            hosts_noncompliant=1,
            snapshot_at=now - timedelta(hours=1),
        )
        rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            baseline="cis",
            score_percent=85.0,
            hosts_in_scope=5,
            hosts_compliant=4,
            hosts_noncompliant=1,
            snapshot_at=now,
        )
        rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=enrolled_site.id,
            baseline="stig",
            score_percent=70.0,
            hosts_in_scope=5,
            hosts_compliant=3,
            hosts_noncompliant=2,
        )
        rsvc.record_vulnerability_rollup_snapshot(
            session, site_id=enrolled_site.id, critical_count=3
        )
        session.commit()

        host, compliance, vuln = rsvc.get_dashboard_rollup(session, enrolled_site.id)
        assert host.host_count == 5
        baselines = {c.baseline: c.score_percent for c in compliance}
        assert baselines == {"cis": 85.0, "stig": 70.0}
        assert vuln.critical_count == 3

    def test_returns_nones_when_empty(self, session, enrolled_site):
        host, compliance, vuln = rsvc.get_dashboard_rollup(session, enrolled_site.id)
        assert host is None
        assert compliance == []
        assert vuln is None


class TestCrossSiteReport:
    def _site(self, session, name):
        site = quick_enroll(session, name=name, url=f"https://{name}.x")
        session.commit()
        return site

    def test_aggregates_across_enrolled_sites(self, session):
        a = self._site(session, "a")
        b = self._site(session, "b")
        rsvc.record_host_rollup_snapshot(
            session, site_id=a.id, host_count=10, active_count=8
        )
        rsvc.record_host_rollup_snapshot(
            session, site_id=b.id, host_count=5, active_count=5
        )
        rsvc.record_vulnerability_rollup_snapshot(
            session, site_id=a.id, critical_count=2, high_count=3
        )
        session.commit()

        report = rsvc.get_cross_site_report(session)
        assert report["totals"]["site_count"] == 2
        assert report["totals"]["host_count"] == 15
        assert report["totals"]["active_count"] == 13
        assert report["totals"]["critical_count"] == 2
        assert {r["site_name"] for r in report["sites"]} == {"a", "b"}

    def test_filters_to_requested_sites(self, session):
        a = self._site(session, "a")
        self._site(session, "b")
        rsvc.record_host_rollup_snapshot(
            session, site_id=a.id, host_count=10, active_count=8
        )
        session.commit()

        report = rsvc.get_cross_site_report(session, [a.id])
        assert report["totals"]["site_count"] == 1
        assert report["sites"][0]["site_name"] == "a"
        assert report["sites"][0]["host_count"] == 10

    def test_worst_compliance_baseline_wins(self, session):
        a = self._site(session, "a")
        rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=a.id,
            baseline="CIS",
            score_percent=92.0,
            hosts_in_scope=10,
            hosts_compliant=9,
            hosts_noncompliant=1,
        )
        rsvc.record_compliance_rollup_snapshot(
            session,
            site_id=a.id,
            baseline="STIG",
            score_percent=61.0,
            hosts_in_scope=10,
            hosts_compliant=6,
            hosts_noncompliant=4,
        )
        session.commit()
        report = rsvc.get_cross_site_report(session, [a.id])
        worst = report["sites"][0]["worst_compliance"]
        assert worst["baseline"] == "STIG"
        assert worst["score_percent"] == 61.0

    def test_empty_when_no_enrolled_sites(self, session):
        report = rsvc.get_cross_site_report(session)
        assert report["totals"]["site_count"] == 0
        assert report["sites"] == []
