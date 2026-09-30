# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Installation evidence for the posture punch list (ROADMAP 21.4 S3).

What ``advisor_engine``'s installation rules read, gathered ONCE per tenant
per tick, in the engine's shape::

    {"domains": {name: {"available": bool}},
     "settings": [{"domain", "key", "value"}],
     "coverage": [{"coverage", "hosts_total", "hosts_ok", "hosts_failing",
                   "hosts_unknown"}]}

The keys per domain are the engine's contract (curated_posture.pxi).

HOW A GAP LOOKS
---------------
Each domain is read on its own. One that raises is LEFT OUT -- the engine
then reports its checks not_assessable (missing) -- never filled with a
default that could read as a passing value. Backups outside multi-tenancy do
not exist at all and are marked unavailable, which the engine says plainly.

SERVER VERSUS TENANT
--------------------
Identity, session, password policy, log forwarding, secrets and the platform
role are SERVER settings (the bootstrap database / sysmanage.yaml), shared by
every tenant; the engine marks their checks ``managed_by: server``. The rest
is read from the tenant's own database.

COVERAGE counts APPROVED hosts. "Unknown" is its own number, never folded
into ok: a host that never reported antivirus state, or whose firewall report
is stale, or whose vulnerability scan has no verdict, is unknown (S0: AV state
existed for 2 of 5 hosts).
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from backend.config import config
from backend.config import settings_service
from backend.persistence import db as dbm
from backend.persistence import models
from backend.persistence.partitions import PARTITION_REGISTRY, partition_session

logger = logging.getLogger(__name__)

# How old a per-host report may be and still count (mirrors the advisor's
# evidence freshness for the same records).
FIREWALL_MAX_AGE = timedelta(days=2)
ANTIVIRUS_MAX_AGE = timedelta(days=7)
COMPLIANCE_MAX_AGE = timedelta(days=30)
VULN_MAX_AGE = timedelta(days=7)


def _flag(value) -> str:
    return "1" if value else "0"


def _rows(domain: str, values: Dict[str, Any]) -> List[Dict[str, str]]:
    return [{"domain": domain, "key": k, "value": str(v)} for k, v in values.items()]


# -- server settings (bootstrap database / yaml) ---------------------------------


def _identity(main) -> Dict[str, Any]:
    mfa = main.query(models.MfaSettings).first()
    admins = [
        u.id for u in main.query(models.User).filter(models.User.is_admin.is_(True))
    ]
    enrolled = 0
    if admins:
        enrolled = (
            main.query(func.count(func.distinct(models.UserMfaEnrollment.user_id)))
            .filter(models.UserMfaEnrollment.user_id.in_(admins))
            .scalar()
        )
    idp = main.query(models.ExternalIdpSettings).first()
    return {
        "mfa_admin_required": _flag(mfa is not None and mfa.admin_required),
        "admins_total": len(admins),
        "admins_mfa_enrolled": int(enrolled or 0),
        "idp_enabled": main.query(models.ExternalIdpProvider)
        .filter(models.ExternalIdpProvider.enabled.is_(True))
        .count(),
        "idp_local_fallback": _flag(idp is None or idp.local_account_fallback),
    }


def _session(_main) -> Dict[str, Any]:
    return {
        "max_failed_logins": int(config.get_max_failed_logins()),
        "session_timeout_seconds": int(config.get_jwt_auth_timeout()),
    }


def _password_policy(_main, tenant_id=None) -> Dict[str, Any]:
    """The EFFECTIVE policy, resolved as login does: the tenant's setting,
    then the server's, then sysmanage.yaml."""
    policy = None
    if tenant_id:
        policy = settings_service.get_tenant_setting(
            str(tenant_id), "password_policy", default=None
        )
    if not isinstance(policy, dict):
        policy = settings_service.get_setting("password_policy", default=None)
    if not isinstance(policy, dict):
        policy = (config.get_config().get("security") or {}).get(
            "password_policy"
        ) or {}
    kinds = sum(
        bool(policy.get(k))
        for k in (
            "require_uppercase",
            "require_lowercase",
            "require_numbers",
            "require_special_chars",
        )
    )
    return {
        "min_length": int(policy.get("min_length", 8)),
        "min_character_types": int(policy.get("min_character_types") or kinds),
    }


def _logging(main) -> Dict[str, Any]:
    syslog = (
        main.query(models.LoggingSetting)
        .filter(models.LoggingSetting.syslog_host.isnot(None))
        .filter(models.LoggingSetting.syslog_host != "")
        .count()
    )
    graylog = (
        main.query(models.GraylogIntegrationSettings)
        .filter(models.GraylogIntegrationSettings.enabled.is_(True))
        .count()
    )
    return {"forward_configured": _flag(syslog or graylog)}


def _secrets(_main) -> Dict[str, Any]:
    return {"openbao_enabled": _flag(config.is_vault_enabled())}


def _platform_role(_main) -> Dict[str, Any]:
    from backend.services import (
        server_config_service,
    )  # noqa: PLC0415 - avoids an import cycle

    return {
        "air_gap_role": server_config_service.get_server_role(),
        "federation_role": server_config_service.get_federation_role(),
    }


# -- tenant settings -------------------------------------------------------------------


def _audit_retention(db) -> Dict[str, Any]:
    days = (
        db.query(func.max(models.AuditRetentionPolicy.retention_days))
        .filter(models.AuditRetentionPolicy.enabled.is_(True))
        .scalar()
    )
    return {"retention_days": int(days or 0)}


def _alerting(db) -> Dict[str, Any]:
    return {
        "channels": db.query(models.NotificationChannel)
        .filter(models.NotificationChannel.enabled.is_(True))
        .count(),
        "rules_enabled": db.query(models.AlertRule)
        .filter(models.AlertRule.enabled.is_(True))
        .count(),
    }


def _patching(db) -> Dict[str, Any]:
    return {
        "upgrade_profiles_enabled": db.query(models.UpgradeProfile)
        .filter(models.UpgradeProfile.enabled.is_(True))
        .count(),
        "allow_windows_enabled": db.query(models.MaintenanceWindow)
        .filter(
            models.MaintenanceWindow.enabled.is_(True),
            models.MaintenanceWindow.kind == "allow",
        )
        .count(),
    }


def _api_keys(main, tenant_id=None) -> Dict[str, Any]:
    query = main.query(models.ApiKey).filter(
        models.ApiKey.is_active.is_(True), models.ApiKey.revoked_at.is_(None)
    )
    if tenant_id:
        query = query.filter(models.ApiKey.tenant_id == tenant_id)
    keys = query.all()
    return {
        "active": len(keys),
        "without_expiry": sum(1 for k in keys if k.expires_at is None),
    }


def _backup(tenant_id, now) -> Optional[Dict[str, Any]]:
    """None when backups cannot exist here (outside multi-tenancy, or the
    bootstrap database): the registry is where backup state lives."""
    if not tenant_id or not (config.get_multitenancy_config() or {}).get("enabled"):
        return None
    from backend.services import tenant_backup  # noqa: PLC0415 - optional subsystem

    rpo = tenant_backup.tenant_rpo_seconds(str(tenant_id))
    with partition_session(PARTITION_REGISTRY) as reg:
        last = (
            reg.query(func.max(models.RegistryTenantBackup.finished_at))
            .filter(
                models.RegistryTenantBackup.tenant_id == tenant_id,
                models.RegistryTenantBackup.kind == models.BACKUP_KIND_BACKUP,
                models.RegistryTenantBackup.status == models.BACKUP_STATUS_SUCCESS,
            )
            .scalar()
        )
    # "Enabled" means backups can actually RUN: per-tenant backups default to
    # on, so a target with no backup command configured on the server is a
    # target nothing will ever meet (found live 2026-09-27: enabled, 24 h RPO,
    # and no backup in the history at all).
    command = tenant_backup.get_backup_config().backup_command
    return {
        "enabled": _flag(rpo and command),
        "rpo_seconds": int(rpo or 0),
        # "Never" is the largest age there is: it can never meet an RPO.
        "last_success_age_seconds": (
            int((now - last).total_seconds()) if last else 10**12
        ),
    }


# -- fleet coverage -----------------------------------------------------------------------


def _coverage(key, states) -> Dict[str, Any]:
    """``states``: one of ok | failing | unknown | None (not applicable)."""
    counted = [s for s in states if s is not None]
    return {
        "coverage": key,
        "hosts_total": len(counted),
        "hosts_ok": counted.count("ok"),
        "hosts_failing": counted.count("failing"),
        "hosts_unknown": counted.count("unknown"),
    }


def _latest_by_host(db, model, time_column, host_ids):
    latest = {}
    for row in (
        db.query(model).filter(model.host_id.in_(host_ids)).order_by(time_column.asc())
    ):
        latest[str(row.host_id)] = row  # ascending: the last one wins
    return latest


def _fips_state(host):
    status = host.fips_status
    if status == "not_applicable":
        return None
    if status == "enabled":
        return "ok"
    if status in ("available", "disabled"):
        return "failing"
    return "unknown"


def _fleet_coverage(db, now) -> List[Dict[str, Any]]:
    hosts = (
        db.query(models.Host).filter(models.Host.approval_status == "approved").all()
    )
    ids = [h.id for h in hosts]
    if not ids:
        return [
            _coverage(key, [])
            for key in (
                "fips",
                "antivirus",
                "firewall",
                "compliance_scan",
                "critical_vulnerabilities",
            )
        ]
    av = _latest_by_host(
        db, models.AntivirusStatus, models.AntivirusStatus.last_updated, ids
    )
    fw = _latest_by_host(
        db, models.FirewallStatus, models.FirewallStatus.last_updated, ids
    )
    comp = _latest_by_host(
        db, models.HostComplianceScan, models.HostComplianceScan.scanned_at, ids
    )
    vuln = _latest_by_host(
        db, models.HostVulnerabilityScan, models.HostVulnerabilityScan.scanned_at, ids
    )

    def av_state(h):
        row = av.get(str(h.id))
        if (
            row is None
            or row.enabled is None
            or row.last_updated is None
            or now - row.last_updated > ANTIVIRUS_MAX_AGE
        ):
            return "unknown"
        return "ok" if row.enabled else "failing"

    def fw_state(h):
        row = fw.get(str(h.id))
        if (
            row is None
            or row.last_updated is None
            or now - row.last_updated > FIREWALL_MAX_AGE
        ):
            return "unknown"
        return "ok" if row.enabled else "failing"

    def comp_state(h):
        row = comp.get(str(h.id))
        # No recent scan is a FAILING coverage, not unknown: "is every host
        # scanned" is exactly what this measures.
        return (
            "ok"
            if row is not None and now - row.scanned_at <= COMPLIANCE_MAX_AGE
            else "failing"
        )

    def vuln_state(h):
        row = vuln.get(str(h.id))
        if (
            row is None
            or now - row.scanned_at > VULN_MAX_AGE
            or (row.risk_level or "").upper() == "UNKNOWN"
        ):
            return "unknown"  # no verdict is not a clean verdict
        return "failing" if (row.critical_count or 0) > 0 else "ok"

    return [
        _coverage("fips", [_fips_state(h) for h in hosts]),
        _coverage("antivirus", [av_state(h) for h in hosts]),
        _coverage("firewall", [fw_state(h) for h in hosts]),
        _coverage("compliance_scan", [comp_state(h) for h in hosts]),
        _coverage("critical_vulnerabilities", [vuln_state(h) for h in hosts]),
    ]


# -- assembly ---------------------------------------------------------------------------------


def _network_discovery(db) -> Dict[str, Any]:
    """21.6 S5: what is on the network that SysManage does not manage.

    Counts come from the same review service the page uses, so the punch
    list and the Network Discovery page can never disagree.
    """
    from backend.services import asset_discovery_review  # noqa: PLC0415

    summary = asset_discovery_review.summary(db)
    return {
        "enabled": _flag(summary["policy"]["enabled"]),
        "unmanaged": summary["counts"]["unmanaged"],
        "networks_with_unmanaged": len(summary["networks"]),
        "observers": len(summary["observers"]),
        "observers_stale": summary["blind_spots"]["stale_observers"],
    }


MALWARE_SCAN_FRESH_DAYS = 30


def _malware(db, now: datetime) -> Dict[str, Any]:
    """21.3 S5: are hosts being scanned, and is anything open?

    Counts come from the same review service the Malware page uses, so the
    punch list and the page can never disagree.  A host counts as UNSCANNED
    when it can scan and has no completed scan in the last 30 days: a clean
    scan from last year proves nothing about today.
    """
    from backend.services import malware_review  # noqa: PLC0415

    summary = malware_review.summary(db)
    latest = malware_review._latest_completed(db)  # pylint: disable=protected-access
    cutoff = now - timedelta(days=MALWARE_SCAN_FRESH_DAYS)
    stale = sum(
        1 for run in latest.values() if run.finished_at and run.finished_at < cutoff
    )
    gaps = summary["blind_spots"]["legs_not_run"]
    return {
        "equipped": summary["coverage"]["equipped"],
        "hosts_unscanned": summary["coverage"]["never_scanned"] + stale,
        "open_high": summary["open_by_severity"]["critical"]
        + summary["open_by_severity"]["high"],
        "legs_skipped": sum(sum(reasons.values()) for reasons in gaps.values()),
    }


def _try(label: str, read: Callable[[], Any]):
    try:
        return read()
    except Exception:  # pylint: disable=broad-except
        # Logged loudly with the domain: an unreadable domain becomes
        # "not assessable", which an operator must be able to trace.
        logger.exception("Posture evidence: could not read %s", label)
        return None


def gather(db, tenant_id=None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The installation evidence for the tenant whose database is ``db``."""
    now = now or datetime.utcnow()
    evidence: Dict[str, Any] = {"domains": {}, "settings": [], "coverage": []}
    main = sessionmaker(bind=dbm.get_engine())()
    try:
        readers = {
            "identity": lambda: _identity(main),
            "session": lambda: _session(main),
            "password_policy": lambda: _password_policy(main, tenant_id),
            "logging": lambda: _logging(main),
            "secrets": lambda: _secrets(main),
            "platform_role": lambda: _platform_role(main),
            "audit_retention": lambda: _audit_retention(db),
            "alerting": lambda: _alerting(db),
            "patching": lambda: _patching(db),
            "api_keys": lambda: _api_keys(main, tenant_id),
        }
        for domain, read in readers.items():
            values = _try(domain, read)
            if values is not None:
                evidence["domains"][domain] = {"available": True}
                evidence["settings"].extend(_rows(domain, values))
        # _backup returns None for "cannot exist here" (unavailable); a read
        # that FAILS must be "missing" instead, so the two are kept apart.
        backup = _try("backup", lambda: {"values": _backup(tenant_id, now)})
        if backup is not None:
            evidence["domains"]["backup"] = {"available": backup["values"] is not None}
            if backup["values"] is not None:
                evidence["settings"].extend(_rows("backup", backup["values"]))
        # Without the licensed engine discovery cannot exist here at all:
        # "unavailable", said plainly -- never a passing zero.
        from backend.services import asset_discovery_shim  # noqa: PLC0415

        if not asset_discovery_shim.engine_available():
            evidence["domains"]["network_discovery"] = {"available": False}
        else:
            discovery = _try("network_discovery", lambda: _network_discovery(db))
            if discovery is not None:
                evidence["domains"]["network_discovery"] = {"available": True}
                evidence["settings"].extend(_rows("network_discovery", discovery))
        from backend.services import malware_shim  # noqa: PLC0415

        if not malware_shim.engine_available():
            evidence["domains"]["malware"] = {"available": False}
        else:
            malware = _try("malware", lambda: _malware(db, now))
            if malware is not None:
                evidence["domains"]["malware"] = {"available": True}
                evidence["settings"].extend(_rows("malware", malware))
        coverage = _try("fleet_coverage", lambda: _fleet_coverage(db, now))
        if coverage is not None:
            evidence["domains"]["fleet_coverage"] = {"available": True}
            evidence["coverage"] = coverage
    finally:
        main.close()
    return evidence
