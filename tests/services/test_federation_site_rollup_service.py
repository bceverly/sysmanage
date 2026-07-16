# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the federation site-side compliance + vulnerability rollup
producers — severity aggregation, latest-scan-per-host compliance rollup, and
the enrolled/empty no-op paths.
"""

import datetime
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence import models  # noqa: F401  # register all models
from backend.persistence.db import Base
from backend.services import federation_coordinator_service as csvc
from backend.services import federation_site_rollup_service as rsvc
from backend.services import federation_sync_queue_service as qsvc


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        with session_factory() as sess:
            yield sess
    finally:
        engine.dispose()


def _enroll(session):
    csvc.start_enrollment(
        session, coordinator_url="https://c", coordinator_tls_cert_pem="c"
    )
    csvc.mark_enrolled(
        session,
        site_id="22222222-2222-2222-2222-222222222222",
        site_tls_cert_pem="site-cert",
    )
    session.commit()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class TestVulnRollup:
    def test_none_when_no_findings(self, session):
        assert rsvc.collect_vulnerability_rollup(session) is None

    def test_aggregates_by_severity(self, session):
        from backend.persistence.models.proplus import (
            HostVulnerabilityFinding,
            HostVulnerabilityScan,
        )

        scan = HostVulnerabilityScan(host_id=uuid.uuid4(), scanned_at=_now())
        session.add(scan)
        session.flush()
        for sev in ("Critical", "high", "HIGH", "low"):  # mixed case on purpose
            session.add(
                HostVulnerabilityFinding(
                    scan_id=scan.id,
                    vulnerability_id=uuid.uuid4(),
                    package_name="pkg",
                    installed_version="1.0",
                    severity=sev,
                )
            )
        session.commit()

        roll = rsvc.collect_vulnerability_rollup(session)
        assert roll["critical_count"] == 1
        assert roll["high_count"] == 2  # case-normalized
        assert roll["low_count"] == 1
        assert roll["affected_host_count"] == 1


class TestComplianceRollup:
    def test_empty_when_no_scans(self, session):
        assert rsvc.collect_compliance_rollups(session) == []

    def test_latest_scan_per_host_per_profile(self, session):
        from backend.persistence.models.proplus import (
            ComplianceProfile,
            HostComplianceScan,
        )

        prof = ComplianceProfile(name="CIS")
        session.add(prof)
        session.flush()
        host1, host2 = uuid.uuid4(), uuid.uuid4()
        # host1: an older non-compliant scan, then a newer compliant one.
        session.add(
            HostComplianceScan(
                host_id=host1,
                profile_id=prof.id,
                scanned_at=_now() - datetime.timedelta(days=1),
                compliance_score=50,
                failed_rules=5,
            )
        )
        session.add(
            HostComplianceScan(
                host_id=host1,
                profile_id=prof.id,
                scanned_at=_now(),
                compliance_score=100,
                failed_rules=0,
            )
        )
        # host2: non-compliant.
        session.add(
            HostComplianceScan(
                host_id=host2,
                profile_id=prof.id,
                scanned_at=_now(),
                compliance_score=80,
                failed_rules=2,
            )
        )
        session.commit()

        rolls = rsvc.collect_compliance_rollups(session)
        assert len(rolls) == 1
        roll = rolls[0]
        assert roll["baseline"] == "CIS"
        assert roll["hosts_in_scope"] == 2
        assert roll["hosts_compliant"] == 1  # host1's latest scan (0 failures)
        assert roll["hosts_noncompliant"] == 1  # host2


class TestHostRollup:
    def test_counts_total_active_and_breakdowns(self, session):
        from backend.persistence.models.core import Host

        session.add_all(
            [
                Host(active=True, fqdn="a", platform="Linux", status="up"),
                Host(active=True, fqdn="b", platform="Linux", status="down"),
                Host(active=False, fqdn="c", platform="Windows", status="up"),
            ]
        )
        session.commit()
        roll = rsvc.collect_host_rollup(session)
        assert roll["host_count"] == 3
        assert roll["active_count"] == 2
        assert roll["os_breakdown"] == {"Linux": 2, "Windows": 1}
        assert roll["status_breakdown"] == {"up": 2, "down": 1}


class TestEnqueue:
    def test_noop_when_unenrolled(self, session):
        assert rsvc.enqueue_vulnerability_rollup(session) is None
        assert rsvc.enqueue_compliance_rollups(session) == 0
        assert rsvc.enqueue_host_rollup(session) is None
        assert qsvc.queue_depth(session) == 0
