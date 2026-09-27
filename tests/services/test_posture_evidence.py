# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Installation evidence for the punch list (21.4 S3), against a real schema.

The properties: an unreadable domain is LEFT OUT (the engine reports it
missing), never defaulted; backups outside multi-tenancy are UNAVAILABLE;
unknown hosts are counted as unknown, never ok -- no report, a stale report
and a scan without a verdict all count as unknown.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import posture_evidence as pe

NOW = datetime(2026, 9, 27, 12, 0, 0)


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with patch.object(pe.dbm, "get_engine", return_value=engine), patch.object(
        pe.config, "get_max_failed_logins", return_value=5
    ), patch.object(pe.config, "get_jwt_auth_timeout", return_value=6000), patch.object(
        pe.config, "is_vault_enabled", return_value=True
    ), patch.object(
        pe.config, "get_multitenancy_config", return_value={"enabled": False}
    ), patch.object(
        pe.settings_service, "get_setting", return_value=None
    ):
        yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _host(db, name, **kw):
    host = models.Host(
        id=uuid.uuid4(), fqdn=name, active=True, approval_status="approved", **kw
    )
    db.add(host)
    db.flush()
    return host


def _settings(evidence):
    return {(s["domain"], s["key"]): s["value"] for s in evidence["settings"]}


def _coverage(evidence):
    return {c["coverage"]: c for c in evidence["coverage"]}


def test_server_and_tenant_settings_are_read(factory):
    with factory() as db:
        db.add(models.User(userid="a@b.c", is_admin=True, active=True))
        db.commit()
        with patch(
            "backend.services.server_config_service.get_server_role",
            return_value="standard",
        ), patch(
            "backend.services.server_config_service.get_federation_role",
            return_value="none",
        ):
            evidence = pe.gather(db, None, NOW)
    s = _settings(evidence)
    assert s[("identity", "admins_total")] == "1"
    assert s[("identity", "admins_mfa_enrolled")] == "0"
    assert s[("identity", "mfa_admin_required")] == "0"
    assert s[("session", "session_timeout_seconds")] == "6000"
    assert s[("secrets", "openbao_enabled")] == "1"
    assert s[("platform_role", "air_gap_role")] == "standard"
    assert s[("alerting", "channels")] == "0"
    assert evidence["domains"]["backup"] == {"available": False}
    assert ("backup", "enabled") not in s


def test_an_unreadable_domain_is_left_out_not_defaulted(factory):
    with factory() as db, patch.object(
        pe, "_audit_retention", side_effect=RuntimeError("boom")
    ):
        evidence = pe.gather(db, None, NOW)
    assert "audit_retention" not in evidence["domains"]
    assert not [s for s in evidence["settings"] if s["domain"] == "audit_retention"]


def test_a_failed_backup_read_is_missing_not_unavailable(factory):
    with factory() as db, patch.object(
        pe, "_backup", side_effect=RuntimeError("registry down")
    ):
        evidence = pe.gather(db, "t1", NOW)
    assert "backup" not in evidence["domains"]


def test_coverage_counts_unknown_hosts_as_unknown(factory):
    with factory() as db:
        ok = _host(db, "ok", fips_status="enabled")
        off = _host(db, "off", fips_status="available")
        _host(db, "na", fips_status="not_applicable")
        silent = _host(db, "silent", fips_status=None)
        db.add(
            models.AntivirusStatus(
                host_id=ok.id, software_name="clamav", enabled=True, last_updated=NOW
            )
        )
        db.add(
            models.AntivirusStatus(
                host_id=off.id, software_name="clamav", enabled=False, last_updated=NOW
            )
        )
        db.add(
            models.FirewallStatus(
                host_id=ok.id,
                firewall_name="ufw",
                enabled=True,
                last_updated=NOW - timedelta(hours=1),
            )
        )
        db.add(
            models.FirewallStatus(
                host_id=off.id,
                firewall_name="ufw",
                enabled=True,
                last_updated=NOW - timedelta(days=5),
            )
        )  # stale
        db.add(
            models.HostVulnerabilityScan(
                host_id=ok.id,
                scanned_at=NOW,
                critical_count=0,
                risk_level="LOW",
                total_packages=1,
            )
        )
        db.add(
            models.HostVulnerabilityScan(
                host_id=off.id,
                scanned_at=NOW,
                critical_count=2,
                risk_level="CRITICAL",
                total_packages=1,
            )
        )
        db.add(
            models.HostVulnerabilityScan(
                host_id=silent.id,
                scanned_at=NOW,
                critical_count=0,
                risk_level="UNKNOWN",
                total_packages=0,
            )
        )
        db.commit()
        cov = _coverage(pe.gather(db, None, NOW))
    assert cov["fips"] == {
        "coverage": "fips",
        "hosts_total": 3,
        "hosts_ok": 1,
        "hosts_failing": 1,
        "hosts_unknown": 1,
    }
    assert (
        cov["antivirus"]["hosts_ok"],
        cov["antivirus"]["hosts_failing"],
        cov["antivirus"]["hosts_unknown"],
    ) == (1, 1, 2)
    assert (cov["firewall"]["hosts_ok"], cov["firewall"]["hosts_unknown"]) == (1, 3)
    # No verdict is not a clean verdict.
    assert (
        cov["critical_vulnerabilities"]["hosts_ok"],
        cov["critical_vulnerabilities"]["hosts_failing"],
        cov["critical_vulnerabilities"]["hosts_unknown"],
    ) == (1, 1, 2)
    # No compliance scan is FAILING coverage: "is every host scanned" is the question.
    assert cov["compliance_scan"]["hosts_failing"] == 4


def test_unapproved_hosts_are_not_counted(factory):
    with factory() as db:
        _host(db, "pending", fips_status="enabled").approval_status = "pending"
        db.commit()
        assert _coverage(pe.gather(db, None, NOW))["fips"]["hosts_total"] == 0
