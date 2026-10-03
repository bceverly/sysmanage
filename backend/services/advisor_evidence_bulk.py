# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Advisor evidence for many hosts at once (Phase 22.3).

``advisor_evidence.gather`` read each domain with its own query per host --
seven a host, every 15 minutes, for every approved host.  This loads a chunk
of hosts' rows per domain in ONE query each and serves ``gather`` from them
(``gather(..., bulk=chunk)``), with exactly the per-host readers' results:
the same rows, the same "at" timestamps, the newest scan only.

Chunked (``CHUNK_HOSTS``): a whole fleet's packages at once would be tens of
millions of rows.  Fact tables (query-pack results) are still read per host;
they only cost anything when a fact rule is enabled.
"""

from typing import Any, Dict, List, Tuple

from sqlalchemy import and_, func

from backend.persistence import models

CHUNK_HOSTS = 250


def _newest(db, model, time_column, host_ids, *filters):
    """Each host's newest ``model`` row (a max-per-host subquery: portable)."""
    newest = (
        db.query(
            model.host_id.label("hid"), func.max(time_column).label("at")
        )  # pylint: disable=not-callable
        .filter(model.host_id.in_(host_ids), *filters)
        .group_by(model.host_id)
        .subquery()
    )
    found = {}
    for row in (
        db.query(model)
        .join(newest, and_(model.host_id == newest.c.hid, time_column == newest.c.at))
        .filter(*filters)
    ):
        found.setdefault(str(row.host_id), row)
    return found


def _grouped(query, key="host_id") -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in query.all():
        data = dict(row._mapping)
        grouped.setdefault(str(data.pop(key)), []).append(data)
    return grouped


def _vuln(db, host_ids):
    scans = _newest(db, models.HostVulnerabilityScan,
                    models.HostVulnerabilityScan.scanned_at, host_ids)  # fmt: skip
    finding = models.HostVulnerabilityFinding
    by_scan = _grouped(
        db.query(finding.scan_id, finding.vulnerability_id, finding.package_name,
                 finding.installed_version, finding.fixed_version, finding.severity,
                 finding.cvss_score)
        .filter(finding.scan_id.in_([s.id for s in scans.values()])),
        key="scan_id",
    )  # fmt: skip
    return {
        hid: (scan.scanned_at, by_scan.get(str(scan.id), []))
        for hid, scan in scans.items()
    }


def _compliance(db, host_ids):
    keep = ("rule_id", "severity", "status", "category")
    scans = _newest(db, models.HostComplianceScan,
                    models.HostComplianceScan.scanned_at, host_ids)  # fmt: skip
    out = {}
    for hid, scan in scans.items():
        results = scan.results if isinstance(scan.results, list) else []
        out[hid] = (scan.scanned_at,
                    [{k: r.get(k) for k in keep} for r in results if isinstance(r, dict)])  # fmt: skip
    return out


def _drift(db, host_ids):
    run = models.ConfigProfileRun
    checked = {
        str(hid): at
        for hid, at in db.query(
            run.host_id, func.max(run.completed_at)
        )  # pylint: disable=not-callable
        .filter(
            run.host_id.in_(host_ids), run.check_mode.is_(True), run.success.is_(True)
        )
        .group_by(run.host_id)
    }
    finding = models.ConfigDriftFinding
    rows = _grouped(
        db.query(finding.host_id, finding.profile_name, finding.task_name,
                 finding.first_seen_at)
        .filter(finding.host_id.in_(host_ids), finding.resolved_at.is_(None))
    )  # fmt: skip
    return {str(h): (checked.get(str(h)), rows.get(str(h), [])) for h in host_ids}


def _updates(db, host_ids, hosts):
    update = models.PackageUpdate
    rows = _grouped(
        db.query(update.host_id, update.package_name, update.update_type,
                 update.package_manager)
        .filter(update.host_id.in_(host_ids), update.status == "available")
    )  # fmt: skip
    return {str(h.id): (h.updates_updated_at, rows.get(str(h.id), [])) for h in hosts}


def _packages(db, host_ids, hosts):
    package = models.SoftwarePackage
    rows = _grouped(
        db.query(package.host_id, package.package_name, package.package_version,
                 package.package_manager)
        .filter(package.host_id.in_(host_ids))
    )  # fmt: skip
    return {str(h.id): (h.software_updated_at, rows.get(str(h.id), [])) for h in hosts}


def _firewall(db, host_ids):
    status = models.FirewallStatus
    found: Dict[str, list] = {}
    for row in db.query(status).filter(status.host_id.in_(host_ids)):
        found.setdefault(str(row.host_id), []).append(row)
    out = {}
    for hid, rows in found.items():
        at = max((r.last_updated for r in rows if r.last_updated), default=None)
        out[hid] = (
            at,
            [{"name": r.firewall_name, "enabled": bool(r.enabled)} for r in rows],
        )
    return out


class Chunk:
    """``domain -> {host_id: (at, rows)}`` for one chunk of hosts."""

    def __init__(self, db, hosts, domains):
        ids = [h.id for h in hosts]
        loaders = {
            "vuln": lambda: _vuln(db, ids),
            "compliance": lambda: _compliance(db, ids),
            "drift": lambda: _drift(db, ids),
            "updates": lambda: _updates(db, ids, hosts),
            "packages": lambda: _packages(db, ids, hosts),
            "firewall": lambda: _firewall(db, ids),
        }
        self.domains = {d: loaders[d]() for d in domains if d in loaders}

    def read(self, domain, host) -> Tuple[Any, List[Dict[str, Any]]]:
        return self.domains[domain].get(str(host.id), (None, []))


def chunks(hosts, size: int = CHUNK_HOSTS):
    for start in range(0, len(hosts), size):
        yield hosts[start : start + size]
