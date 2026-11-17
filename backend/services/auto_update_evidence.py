# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What a host's pending updates fix, for the waiting periods (ROADMAP 26.3).

The automation engine decides whether a patch is critical; this module only
reads the rows it decides from, per package name:

  * ``findings``: the host's latest vulnerability scan (``vuln_engine``),
    each ``{"id": CVE, "severity": as rated for this host, "fixed_version"}``
  * ``advisories``: the vendor advisories that apply to the host
    (``advisory_engine``), each ``{"id", "severity", "fixed_version",
    "published"}`` -- the vendor's release date counts toward the wait

and which of the two sources the host has data from at all: without it, a
critical count never applies and everything waits the regular count.
"""

import logging
from typing import Any, Dict, List

from backend.persistence import models

logger = logging.getLogger(__name__)

VULNERABILITY = "vulnerability"
ADVISORY = "advisory"


def _loaded(code: str) -> bool:
    from backend.licensing.module_loader import (  # pylint: disable=import-outside-toplevel
        module_loader,
    )

    return module_loader.get_module(code) is not None


def _shared(query_fn, default):
    """Read the shared partition (CVE ids, advisory dates); never raises."""
    from backend.persistence.partitions import (  # pylint: disable=import-outside-toplevel
        shared_sessionmaker,
    )

    try:
        session = shared_sessionmaker()()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Automatic updates: no shared session for CVE data")
        return default
    try:
        return query_fn(session)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Automatic updates: reading shared CVE data failed")
        return default
    finally:
        session.close()


def _findings(db, host_id) -> List[Dict[str, Any]]:
    scan = (
        db.query(models.HostVulnerabilityScan)
        .filter(models.HostVulnerabilityScan.host_id == host_id)
        .order_by(models.HostVulnerabilityScan.scanned_at.desc())
        .first()
    )
    if scan is None:
        return []
    finding = models.HostVulnerabilityFinding
    rows = (
        db.query(
            finding.vulnerability_id,
            finding.package_name,
            finding.fixed_version,
            finding.severity,
        )
        .filter(finding.scan_id == scan.id)
        .all()
    )
    ids = {row.vulnerability_id for row in rows}
    cves = _shared(
        lambda s: dict(
            s.query(models.Vulnerability.id, models.Vulnerability.cve_id).filter(
                models.Vulnerability.id.in_(list(ids))
            )
        ),
        {},
    )
    return [
        {
            "package_name": row.package_name,
            "id": cves.get(row.vulnerability_id) or str(row.vulnerability_id),
            "severity": row.severity,
            "fixed_version": row.fixed_version,
        }
        for row in rows
    ]


def _advisories(db, host_id) -> List[Dict[str, Any]]:
    applicable = models.HostApplicableAdvisory
    rows = (
        db.query(applicable)
        .filter(applicable.host_id == host_id, applicable.status == "applicable")
        .all()
    )
    ids = {row.advisory_id for row in rows}
    published = _shared(
        lambda s: dict(
            s.query(models.SharedAdvisory.id, models.SharedAdvisory.published_date)
            .filter(models.SharedAdvisory.id.in_(list(ids)))
            .all()
        ),
        {},
    )
    return [
        {
            "package_name": row.package_name,
            "id": row.advisory_identifier,
            "severity": row.severity,
            "fixed_version": row.fixed_version,
            "published": published.get(row.advisory_id),
        }
        for row in rows
    ]


def sources(db, host_id) -> Dict[str, bool]:
    """Which data this host's critical decisions can come from."""
    has_scan = (
        db.query(models.HostVulnerabilityScan.id)
        .filter(models.HostVulnerabilityScan.host_id == host_id)
        .first()
        is not None
    )
    return {
        VULNERABILITY: _loaded("vuln_engine") and has_scan,
        ADVISORY: _loaded("advisory_engine"),
    }


def attach(db, host_id, updates: List[Dict[str, Any]]) -> Dict[str, bool]:
    """Add ``findings`` and ``advisories`` to each update dict (by package
    name), from the sources the host has; return those sources."""
    have = sources(db, host_id)
    by_package: Dict[str, Dict[str, list]] = {}
    if have[VULNERABILITY]:
        for row in _findings(db, host_id):
            by_package.setdefault(row.pop("package_name"), {}).setdefault(
                "findings", []
            ).append(row)
    if have[ADVISORY]:
        for row in _advisories(db, host_id):
            by_package.setdefault(row.pop("package_name"), {}).setdefault(
                "advisories", []
            ).append(row)
    for update in updates:
        found = by_package.get(update["package_name"], {})
        update["findings"] = found.get("findings", [])
        update["advisories"] = found.get("advisories", [])
    return have
