# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Gather one host's evidence for the advisor (ROADMAP 21.2 S2).

The licensed ``advisor_engine`` decides every outcome; it has no database.
This module reads what the rules may need and hands it over as plain data in
the two shapes the engine takes:

* ``evidence`` -- what was MEASURED, and when:
  ``{"facts": {table: {"gap", "collected_at"}}, "domains": {domain: {"at"}}}``.
  The engine resolves every rule's requirements against this BEFORE any SQL
  runs, so a host without the evidence is not_assessable, never "clean".
* ``tables`` -- the rows the rules' SQL reads: fact tables by their osquery
  names, plus the ``sm_*`` views of server records.

EACH DOMAIN HAS ITS OWN CLOCK
-----------------------------
A heartbeat proves the agent is alive, not that its update list is current.
Every domain's ``at`` is read from the record that domain's own collector
stamps (the table in ``advisor_engine``'s rule_contract.pxi is the reference),
and a domain that never reported is ``at: None`` -- "missing", which the
engine reports distinctly from "stale".

FACTS: SERVED, COLLECTED, FRESH -- THREE QUESTIONS
--------------------------------------------------
``host_facts.missing_columns`` answers the first (per COLUMN: a served table
whose provider leaves the rule's columns NULL is not evidence). The server
stores fact rows only as query-pack results, so the second and third come
from the newest result of the query named ``advisor.<table>`` for the host --
the advisor's own collection, which the engine does not dispatch in S2. Until
something collects them, every fact rule is ``not_collected``: honest, and
visible, rather than evaluated against nothing.
"""

import logging
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import host_facts

logger = logging.getLogger(__name__)

# Query-pack query names the advisor reads fact rows from: one query per
# contract table, ``SELECT *`` over it.
FACT_QUERY_PREFIX = "advisor."


def required(rules: Iterable[Dict[str, Any]]) -> Tuple[Dict[str, Set[str]], Set[str]]:
    """``({fact table: columns}, {domains})`` any of ``rules`` reads.

    Only these are gathered: a tenant with no vuln rule must not pay for
    reading every host's findings on every tick.
    """
    tables: Dict[str, Set[str]] = {}
    domains: Set[str] = set()
    for rule in rules or ():
        requires = (rule or {}).get("requires") or {}
        facts = requires.get("facts") or {}
        if isinstance(facts, dict):
            for table, columns in facts.items():
                tables.setdefault(table, set()).update(columns or ())
        domains.update(d for d in requires.get("domains") or () if isinstance(d, str))
    return tables, domains


def _rows(query) -> List[Dict[str, Any]]:
    return [dict(row._mapping) for row in query.all()]


def _vuln(db: Session, host) -> Tuple[Any, List[Dict[str, Any]]]:
    scan = (
        db.query(models.HostVulnerabilityScan)
        .filter(models.HostVulnerabilityScan.host_id == host.id)
        .order_by(models.HostVulnerabilityScan.scanned_at.desc())
        .first()
    )
    if scan is None:
        return None, []
    finding = models.HostVulnerabilityFinding
    rows = _rows(
        db.query(
            finding.vulnerability_id,
            finding.package_name,
            finding.installed_version,
            finding.fixed_version,
            finding.severity,
            finding.cvss_score,
        ).filter(finding.scan_id == scan.id)
    )
    return scan.scanned_at, rows


def _compliance(db: Session, host) -> Tuple[Any, List[Dict[str, Any]]]:
    scan = (
        db.query(models.HostComplianceScan)
        .filter(models.HostComplianceScan.host_id == host.id)
        .order_by(models.HostComplianceScan.scanned_at.desc())
        .first()
    )
    if scan is None:
        return None, []
    results = scan.results if isinstance(scan.results, list) else []
    keep = ("rule_id", "severity", "status", "category")
    return scan.scanned_at, [
        {k: r.get(k) for k in keep} for r in results if isinstance(r, dict)
    ]


def _drift(db: Session, host) -> Tuple[Any, List[Dict[str, Any]]]:
    # A drift FINDING only records divergence; its absence proves nothing.
    # What proves the host was checked is a SUCCESSFUL check-mode run.
    run = models.ConfigProfileRun
    at = (
        db.query(func.max(run.completed_at))
        .filter(run.host_id == host.id, run.check_mode.is_(True), run.success.is_(True))
        .scalar()
    )
    finding = models.ConfigDriftFinding
    rows = _rows(
        db.query(finding.profile_name, finding.task_name, finding.first_seen_at).filter(
            finding.host_id == host.id, finding.resolved_at.is_(None)
        )
    )
    return at, rows


def _updates(db: Session, host) -> Tuple[Any, List[Dict[str, Any]]]:
    update = models.PackageUpdate
    rows = _rows(
        db.query(
            update.package_name, update.update_type, update.package_manager
        ).filter(update.host_id == host.id, update.status == "available")
    )
    return host.updates_updated_at, rows


def _packages(db: Session, host) -> Tuple[Any, List[Dict[str, Any]]]:
    package = models.SoftwarePackage
    rows = _rows(
        db.query(
            package.package_name, package.package_version, package.package_manager
        ).filter(package.host_id == host.id)
    )
    return host.software_updated_at, rows


def _firewall(db: Session, host) -> Tuple[Any, List[Dict[str, Any]]]:
    status = models.FirewallStatus
    found = db.query(status).filter(status.host_id == host.id).all()
    at = max((r.last_updated for r in found if r.last_updated), default=None)
    return at, [{"name": r.firewall_name, "enabled": bool(r.enabled)} for r in found]


# domain -> (reader, the sm_* view its rows fill, or None)
_DOMAINS = {
    "vuln": (_vuln, "sm_vuln_finding"),
    "compliance": (_compliance, "sm_compliance_result"),
    "drift": (_drift, "sm_drift_finding"),
    "updates": (_updates, "sm_pending_update"),
    "packages": (_packages, "sm_package"),
    "firewall": (_firewall, "sm_firewall"),
}


def _sm_host(host) -> Dict[str, Any]:
    return {
        "fqdn": host.fqdn,
        "platform": host.platform,
        "platform_release": host.platform_release,
        "reboot_required": bool(host.reboot_required),
        "reboot_required_reason": host.reboot_required_reason,
        "reboot_required_updated_at": host.reboot_required_updated_at,
    }


def _fact_rows(db: Session, host, table: str) -> Tuple[Any, List[Dict[str, Any]]]:
    """``(collected_at, rows)`` from the newest ``advisor.<table>`` result.

    ``(None, [])`` when no such query has ever answered, or when its newest
    answer was an error -- neither is a collection. An ``ok`` answer with no
    rows IS one (the table is empty on the host): the result handler stores a
    single payload-less row for it, which is how the two stay apart.
    """
    result = models.QueryPackResultRow
    run = models.QueryPackRun
    name = FACT_QUERY_PREFIX + table
    newest = (
        db.query(result.run_id, result.status, result.collected_at)
        .join(run, run.id == result.run_id)
        .filter(run.host_id == host.id, result.query_name == name)
        .order_by(result.collected_at.desc())
        .first()
    )
    if newest is None or newest.status != models.QUERY_STATUS_OK:
        return None, []
    rows = [
        r.columns
        for r in db.query(result.columns).filter(
            result.run_id == newest.run_id, result.query_name == name
        )
        if isinstance(r.columns, dict)
    ]
    return newest.collected_at, rows


def gather(
    db: Session,
    host,
    fact_needs: Dict[str, Set[str]],
    domains: Set[str],
) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
    """``(evidence, tables)`` for one host -- see the module docstring."""
    evidence: Dict[str, Any] = {"facts": {}, "domains": {}}
    tables: Dict[str, List[Dict[str, Any]]] = {"sm_host": [_sm_host(host)]}

    for domain in sorted(domains):
        if domain == "reboot":
            evidence["domains"][domain] = {"at": host.reboot_required_updated_at}
        elif domain in _DOMAINS:
            reader, view = _DOMAINS[domain]
            at, rows = reader(db, host)
            evidence["domains"][domain] = {"at": at}
            tables[view] = rows
        # Anything else (metric_history, or a domain this server does not
        # know) is left out: the engine reports it domain_unavailable.

    for table, columns in sorted(fact_needs.items()):
        gap: Optional[Dict[str, Any]] = host_facts.missing_columns(
            host, table, sorted(columns)
        )
        collected_at, rows = (
            (None, []) if gap is not None else _fact_rows(db, host, table)
        )
        evidence["facts"][table] = {"gap": gap, "collected_at": collected_at}
        if rows:
            tables[table] = rows
    return evidence, tables


def peer_value(host, peer_group: Optional[str], tag_ids=None) -> Optional[str]:
    """The host's value for a fleet rule's ``peer_group``, or None.

    None means the host has no peers under that grouping -- the engine then
    reports it not_assessable rather than comparing it with hosts it is not
    like (S0: Ubuntu's backported curl judged against the BSDs').
    """
    if peer_group == "os_release":
        if not host.platform:
            return None
        return f"{host.platform} {host.platform_release or ''}".strip()
    if peer_group == "site":
        site = getattr(host, "site_id", None)
        return str(site) if site else None
    if peer_group == "tag":
        # One tag group per host would be arbitrary with several tags; the
        # sorted set is the peer identity.
        return ",".join(sorted(str(t) for t in tag_ids)) if tag_ids else None
    # ``package_manager`` is in the contract, but a host has several (apt AND
    # snap AND flatpak) and nothing records which one "is" the host's, so
    # there is no honest single value yet: its fleet rules are not_assessable
    # (peer_group missing) until one is defined.
    return None
