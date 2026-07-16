# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Smoke tests for the Phase 14.1 advisory schema (models + partitions).

Validates the shared catalog (advisory + packages + advisory↔CVE links, with
intra-shared cascade) and the tenant-partition applicability row whose
``advisory_id`` is a SOFT cross-partition reference to ``shared_advisory.id``.
"""

import uuid
from datetime import datetime

from backend.persistence.models import (
    Host,
    HostApplicableAdvisory,
    SharedAdvisory,
    SharedAdvisoryCve,
    SharedAdvisoryPackage,
    Vulnerability,
)

NOW = datetime(2026, 7, 12, 12, 0)


def _make_advisory(db):
    adv = SharedAdvisory(
        advisory_id="USN-6700-1",
        source="ubuntu",
        advisory_type="security",
        severity="HIGH",
        title="Kernel vulnerabilities",
        affected_releases=["ubuntu:22.04", "ubuntu:24.04"],
        references=["https://ubuntu.com/security/notices/USN-6700-1"],
    )
    adv.packages.append(
        SharedAdvisoryPackage(
            package_name="linux-image-generic",
            package_manager="apt",
            release="ubuntu:22.04",
            fixed_version="5.15.0-101.111",
        )
    )
    db.add(adv)
    db.flush()
    return adv


class TestSharedCatalog:
    def test_advisory_with_packages_and_cve_links(self, db_session):
        # A real CVE row so the intra-shared FK resolves.
        vuln = Vulnerability(cve_id="CVE-2024-1000", severity="HIGH")
        db_session.add(vuln)
        db_session.flush()

        adv = _make_advisory(db_session)
        db_session.add(
            SharedAdvisoryCve(
                advisory_row_id=adv.id,
                vulnerability_id=vuln.id,
                cve_id="CVE-2024-1000",
            )
        )
        db_session.commit()

        loaded = (
            db_session.query(SharedAdvisory)
            .filter(SharedAdvisory.advisory_id == "USN-6700-1")
            .first()
        )
        d = loaded.to_dict(include_packages=True)
        assert d["source"] == "ubuntu"
        assert d["cve_ids"] == ["CVE-2024-1000"]
        assert d["packages"][0]["package_name"] == "linux-image-generic"
        assert d["affected_releases"] == ["ubuntu:22.04", "ubuntu:24.04"]

    def test_intra_shared_cascade_delete(self, db_session):
        adv = _make_advisory(db_session)
        db_session.add(
            SharedAdvisoryCve(
                advisory_row_id=adv.id, vulnerability_id=None, cve_id="CVE-2024-2"
            )
        )
        db_session.commit()
        adv_id = adv.id

        db_session.delete(adv)
        db_session.commit()

        assert (
            db_session.query(SharedAdvisoryPackage)
            .filter(SharedAdvisoryPackage.advisory_row_id == adv_id)
            .count()
            == 0
        )
        assert (
            db_session.query(SharedAdvisoryCve)
            .filter(SharedAdvisoryCve.advisory_row_id == adv_id)
            .count()
            == 0
        )


class TestTenantApplicability:
    def test_soft_ref_to_shared_advisory(self, db_session):
        adv = _make_advisory(db_session)
        db_session.commit()

        host = Host(fqdn="web01.example", active=True, approval_status="approved")
        db_session.add(host)
        db_session.flush()

        applicable = HostApplicableAdvisory(
            host_id=host.id,
            advisory_id=adv.id,  # soft ref — no FK
            advisory_identifier=adv.advisory_id,
            source=adv.source,
            advisory_type=adv.advisory_type,
            severity=adv.severity,
            package_name="linux-image-generic",
            installed_version="5.15.0-100.110",
            fixed_version="5.15.0-101.111",
            computed_at=NOW,
        )
        db_session.add(applicable)
        db_session.commit()

        row = db_session.query(HostApplicableAdvisory).first()
        assert row.advisory_identifier == "USN-6700-1"
        assert row.to_dict()["severity"] == "HIGH"

        # Resolve the soft ref against the (here, same) shared catalog.
        resolved = (
            db_session.query(SharedAdvisory)
            .filter(SharedAdvisory.id == row.advisory_id)
            .first()
        )
        assert resolved is not None
        assert resolved.advisory_id == "USN-6700-1"

    def test_unique_constraint_host_advisory_package(self, db_session):
        import pytest
        from sqlalchemy.exc import IntegrityError

        adv_id = uuid.uuid4()
        host = Host(fqdn="db01.example", active=True, approval_status="approved")
        db_session.add(host)
        db_session.flush()

        def _row():
            return HostApplicableAdvisory(
                host_id=host.id,
                advisory_id=adv_id,
                advisory_identifier="RHSA-2024:1",
                package_name="openssl",
                computed_at=NOW,
            )

        db_session.add(_row())
        db_session.commit()
        db_session.add(_row())  # duplicate (host, advisory, package)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
