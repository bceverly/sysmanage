# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.3: advisor evidence loaded for a chunk of hosts at once must be
exactly what the per-host readers return -- same rows, same timestamps, the
newest scan only.  Real database; varied hosts (some with nothing at all)."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import event

from backend.persistence import models
from backend.services import advisor_evidence as ev
from backend.services import advisor_evidence_bulk as bulk_ev

NOW = datetime.now(timezone.utc).replace(tzinfo=None)
DOMAINS = {"vuln", "compliance", "drift", "updates", "packages", "firewall", "reboot"}


def _seed(db, count=7):
    hosts = []
    for i in range(count):
        host = models.Host(id=uuid.uuid4(), fqdn=f"e{i}.example.com", active=True,
                           approval_status="approved", platform="Linux",
                           software_updated_at=NOW - timedelta(hours=i),
                           updates_updated_at=NOW - timedelta(hours=2 * i))  # fmt: skip
        db.add(host)
        hosts.append(host)
        db.flush()
        if i == 0:
            continue  # a host with no evidence at all
        for j in range(i % 3 + 1):
            db.add(models.SoftwarePackage(id=uuid.uuid4(), host_id=host.id,
                                          package_name=f"p{j}", package_version=f"1.{i}",
                                          package_manager="apt", created_at=NOW,
                                          updated_at=NOW))  # fmt: skip
        db.add(models.PackageUpdate(id=uuid.uuid4(), host_id=host.id, package_name="openssl",
                                    current_version="1", available_version="2",
                                    package_manager="apt", update_type="security",
                                    status="available" if i % 2 else "installed",
                                    discovered_at=NOW, created_at=NOW,
                                    updated_at=NOW))  # fmt: skip
        for age, crit in ((48, 1), (1, i)):  # an older scan, then the newest
            scan = models.HostVulnerabilityScan(id=uuid.uuid4(), host_id=host.id,
                                                scanned_at=NOW - timedelta(hours=age),
                                                critical_count=crit)  # fmt: skip
            db.add(scan)
            db.flush()
            db.add(models.HostVulnerabilityFinding(id=uuid.uuid4(), scan_id=scan.id,
                                                   vulnerability_id=uuid.uuid4(),
                                                   package_name="openssl",
                                                   installed_version="1", severity="HIGH",
                                                   cvss_score=7.5))  # fmt: skip
        db.add(models.HostComplianceScan(id=uuid.uuid4(), host_id=host.id,
                                         scanned_at=NOW - timedelta(hours=i),
                                         results=[{"rule_id": f"r{i}", "severity": "high",
                                                   "status": "fail", "category": "x",
                                                   "extra": "dropped"}]))  # fmt: skip
        db.add(models.FirewallStatus(id=uuid.uuid4(), host_id=host.id, firewall_name="ufw",
                                     enabled=bool(i % 2), last_updated=NOW))  # fmt: skip
        if i % 2:
            db.add(models.ConfigDriftFinding(id=uuid.uuid4(), host_id=host.id,
                                             profile_name="base", task_name=f"t{i}",
                                             first_seen_at=NOW - timedelta(hours=i),
                                             last_seen_at=NOW))  # fmt: skip
    db.commit()
    return hosts


def _canon(evidence, tables):
    return evidence, {k: sorted(map(repr, v)) for k, v in tables.items()}


def test_bulk_evidence_is_exactly_the_per_host_evidence(session):
    hosts = _seed(session)
    chunk = bulk_ev.Chunk(session, hosts, DOMAINS)
    for host in hosts:
        assert _canon(*ev.gather(session, host, {}, DOMAINS, bulk=chunk)) == _canon(
            *ev.gather(session, host, {}, DOMAINS)
        ), host.fqdn


def test_a_chunk_reads_each_domain_once_not_once_per_host(session):
    _seed(session, count=20)
    hosts = session.query(models.Host).all()  # loaded, as the tick loads them
    statements = []
    engine = session.get_bind()

    def listener(*args):
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", listener)
    try:
        chunk = bulk_ev.Chunk(session, hosts, DOMAINS)
        for host in hosts:
            ev.gather(session, host, {}, DOMAINS, bulk=chunk)
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(statements) <= 9  # ~1-2 per domain for all 20 hosts


def test_chunks_cover_every_host_once():
    hosts = list(range(23))
    seen = [h for chunk in bulk_ev.chunks(hosts, size=10) for h in chunk]
    assert seen == hosts
