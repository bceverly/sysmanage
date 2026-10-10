# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Closing the loop: remedies for open posture items (ROADMAP 21.4 S5).

A curated check names a ``remedy`` id; THIS module owns what each id does,
because every one of them is a server capability that already exists:

* ``setting`` -- a server setting (MFA for administrators, the lockout
  threshold, the session timeout), changed when an administrator applies it.
* ``fleet`` -- one command per FAILING host through the path that already
  does it (the FIPS, firewall and antivirus plan builders + the outbound
  queue), so maintenance windows gate it exactly as they gate the per-host
  buttons. Only the hosts the item counted as failing are touched.
* ``guided`` -- no safe automatic change exists (it needs a choice only the
  operator can make: where logs go, which channel pages whom). The server
  names the UI AREA; the UI owns the link.
* ``none`` -- nothing in SysManage can change it (the password policy lives
  in sysmanage.yaml). Said plainly, never a dead button.

Every preview is exactly what apply would do; apply needs an ADMINISTRATOR
**and** the role the underlying per-host action needs, so the posture page
never widens anyone's permissions. Every application is audited and leaves a
``remediation_requested`` event on the item. Under multi-tenancy a
server-managed item offers nothing to a tenant: only the server operator can
change a setting every tenant shares.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.config import config, settings_service
from backend.persistence import models
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType

logger = logging.getLogger(__name__)

KIND_SETTING = "setting"
KIND_FLEET = "fleet"
KIND_GUIDED = "guided"
KIND_NONE = "none"

# Why a remedy cannot be applied right now (codes; the UI words them).
UNAVAILABLE_UNKNOWN = "unknown_remedy"
UNAVAILABLE_SERVER_MANAGED = "managed_by_server"
UNAVAILABLE_NOT_OPEN = "not_open"
UNAVAILABLE_NOTHING_TO_DO = "nothing_to_do"
UNAVAILABLE_NOT_AUTOMATED = "not_automated"

TARGET_SESSION_TIMEOUT = 3600
TARGET_MAX_FAILED_LOGINS = 5
FIREWALL_FRESH = timedelta(days=2)
ANTIVIRUS_FRESH = timedelta(days=7)

# Guided remedies: the UI area each one sends the operator to.
GUIDED = {
    "enroll_admin_mfa": "user_security",
    "configure_log_forwarding": "logging_settings",
    "set_audit_retention": "audit_retention",
    "configure_alerting": "alerting",
    "schedule_security_updates": "upgrade_profiles",
    "define_maintenance_windows": "maintenance_windows",
    "configure_backups": "tenant_backups",
    "set_air_gap_role": "server_role",
    "expire_api_keys": "api_keys",
    "run_compliance_scans": "compliance",
    "patch_critical_vulnerabilities": "advisor_proposals",
    "enable_openbao": "secrets",
    # 21.6 S5: both are decisions an operator takes on the discovery page.
    "enable_network_discovery": "asset_discovery",
    "review_unmanaged_devices": "asset_discovery",
    # 21.3 S5: scans and findings are both handled on the Malware page.
    "scan_for_malware": "malware",
    "review_malware_findings": "malware",
}
NONE = {"set_password_policy"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _multitenant() -> bool:
    return bool((config.get_multitenancy_config() or {}).get("enabled"))


# -- settings ----------------------------------------------------------------------------


def _main_session():
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence import db as dbm  # noqa: PLC0415

    return sessionmaker(bind=dbm.get_engine())()


def _mfa_change() -> List[Dict[str, Any]]:
    from backend.services import mfa_service  # noqa: PLC0415

    with _main_session() as main:
        current = bool(mfa_service.get_settings(main).admin_required)
    return (
        []
        if current
        else [{"setting": "mfa_admin_required", "from": False, "to": True}]
    )


def _apply_mfa(_change=None) -> None:
    from backend.services import mfa_service  # noqa: PLC0415

    with _main_session() as main:
        row = mfa_service.get_settings(main)
        row.admin_required = True
        main.merge(row)
        main.commit()


def _setting_change(key, current, target, ok) -> List[Dict[str, Any]]:
    return [] if ok(current) else [{"setting": key, "from": current, "to": target}]


def _set(change) -> None:
    # set_setting reports failure by RETURNING False; a remedy that ignored
    # it would claim a change that never happened.
    if not settings_service.set_setting(change["setting"], change["to"]):
        raise RuntimeError(f"setting not persisted: {change['setting']}")


SETTINGS = {
    "require_admin_mfa": (_mfa_change, _apply_mfa),
    "enforce_lockout": (
        lambda: _setting_change(
            "max_failed_logins",
            config.get_max_failed_logins(),
            TARGET_MAX_FAILED_LOGINS,
            lambda v: 1 <= int(v) <= 10,
        ),
        _set,
    ),
    "shorten_session": (
        lambda: _setting_change(
            "jwt_auth_timeout",
            config.get_jwt_auth_timeout(),
            TARGET_SESSION_TIMEOUT,
            lambda v: 1 <= int(v) <= TARGET_SESSION_TIMEOUT,
        ),
        _set,
    ),
}


# -- fleet ------------------------------------------------------------------------------------


def _approved(db):
    return db.query(models.Host).filter(models.Host.approval_status == "approved").all()


def _latest(db, model, column, host_ids):
    latest = {}
    for row in (
        db.query(model).filter(model.host_id.in_(host_ids)).order_by(column.asc())
    ):
        latest[str(row.host_id)] = row
    return latest


def _fips_hosts(db):
    return [h for h in _approved(db) if h.fips_status in ("available", "disabled")]


def _firewall_hosts(db):
    hosts = _approved(db)
    rows = _latest(
        db,
        models.FirewallStatus,
        models.FirewallStatus.last_updated,
        [h.id for h in hosts],
    )
    now = _now()
    return [
        h
        for h in hosts
        if (r := rows.get(str(h.id))) is not None
        and r.enabled is False
        and r.last_updated is not None
        and now - r.last_updated <= FIREWALL_FRESH
    ]


def _antivirus_hosts(db):
    hosts = _approved(db)
    rows = _latest(
        db,
        models.AntivirusStatus,
        models.AntivirusStatus.last_updated,
        [h.id for h in hosts],
    )
    now = _now()
    # Only an INSTALLED, disabled antivirus is enabled here; a host with none
    # needs a product chosen for it, which is the antivirus page's job.
    return [
        h
        for h in hosts
        if (r := rows.get(str(h.id))) is not None
        and r.enabled is False
        and r.last_updated is not None
        and now - r.last_updated <= ANTIVIRUS_FRESH
    ]


def _dispatch_fips(db, host, user):
    from backend.api import fips_actions  # noqa: PLC0415

    fips_actions._change_fips(  # pylint: disable=protected-access
        str(host.id), True, fips_actions.FipsChangeRequest(), db, user.userid
    )


def _dispatch_firewall(db, host, _user):
    from backend.api import firewall_status  # noqa: PLC0415
    from backend.services import firewall_plan_builder  # noqa: PLC0415

    plan = firewall_plan_builder.build_enable_plan(
        firewall_status._host_info_for_planner(host)  # pylint: disable=protected-access
    )
    firewall_status._queue_apply_deployment_plan(
        db, host, plan
    )  # pylint: disable=protected-access


def _dispatch_antivirus(db, host, _user):
    from backend.api import antivirus_status, firewall_status  # noqa: PLC0415
    from backend.services import av_plan_builder  # noqa: PLC0415

    plan = av_plan_builder.build_enable_plan(
        antivirus_status._host_info_for_av_planner(
            host
        )  # pylint: disable=protected-access
    )
    # The same APPLY_DEPLOYMENT_PLAN wrapping the antivirus route builds inline.
    firewall_status._queue_apply_deployment_plan(
        db, host, plan
    )  # pylint: disable=protected-access


# Per-host failure codes in an apply() result; the UI translates each.
FAILURE_UNSUPPORTED_PLATFORM = "unsupported_platform"
FAILURE_DISPATCH = "dispatch_failed"


def _failure_code(exc: Exception) -> str:
    """The code for one host's failure: a planner that has no plan for the
    host's platform refuses with ValueError or a failed lookup; anything else
    is a dispatch failure."""
    if isinstance(exc, (ValueError, LookupError)):
        return FAILURE_UNSUPPORTED_PLATFORM
    return FAILURE_DISPATCH


# (hosts to act on, per-host dispatch, the role the per-host button needs)
FLEET = {
    "enable_fips": (_fips_hosts, _dispatch_fips, None),
    "enable_firewall": (
        _firewall_hosts,
        _dispatch_firewall,
        SecurityRoles.ENABLE_FIREWALL,
    ),
    "enable_antivirus": (
        _antivirus_hosts,
        _dispatch_antivirus,
        SecurityRoles.ENABLE_ANTIVIRUS,
    ),
}


def kind_of(remedy: Optional[str]) -> Optional[str]:
    if remedy in SETTINGS:
        return KIND_SETTING
    if remedy in FLEET:
        return KIND_FLEET
    if remedy in GUIDED:
        return KIND_GUIDED
    if remedy in NONE:
        return KIND_NONE
    return None


# -- preview + apply ---------------------------------------------------------------------------


def preview(db, item, rule: Dict[str, Any]) -> Dict[str, Any]:
    """Exactly what apply() would do for this item, and whether it can."""
    remedy = (rule or {}).get("remedy")
    kind = kind_of(remedy)
    out: Dict[str, Any] = {
        "remedy": remedy,
        "kind": kind,
        "available": False,
        "unavailable_reason": None,
        "target": GUIDED.get(remedy),
        "changes": [],
        "hosts": [],
    }
    if kind is None:
        out["unavailable_reason"] = UNAVAILABLE_UNKNOWN
    elif kind in (KIND_GUIDED, KIND_NONE):
        out["unavailable_reason"] = UNAVAILABLE_NOT_AUTOMATED
    elif item.state != models.POSTURE_OPEN:
        out["unavailable_reason"] = UNAVAILABLE_NOT_OPEN
    elif item.managed_by == "server" and _multitenant():
        out["unavailable_reason"] = UNAVAILABLE_SERVER_MANAGED
    elif kind == KIND_SETTING:
        out["changes"] = SETTINGS[remedy][0]()
    else:
        out["hosts"] = [{"id": str(h.id), "fqdn": h.fqdn} for h in FLEET[remedy][0](db)]
    if out["unavailable_reason"] is None:
        if out["changes"] or out["hosts"]:
            out["available"] = True
        else:
            out["unavailable_reason"] = UNAVAILABLE_NOTHING_TO_DO
    return out


def required_role(rule: Dict[str, Any]):
    remedy = (rule or {}).get("remedy")
    return FLEET[remedy][2] if remedy in FLEET else None


def _audit(user, entity_type, description, details) -> None:
    with _main_session() as main:
        AuditService.log(
            db=main,
            action_type=ActionType.EXECUTE,
            entity_type=entity_type,
            description=description,
            user_id=getattr(user, "id", None),
            username=getattr(user, "userid", None),
            entity_name=details.get("rule_key"),
            details=details,
            category="security",
        )


def apply(db, scope, item, rule, user, threat_model_version=None) -> Dict[str, Any]:
    """Carry out the preview. Returns ``{applied, changes, hosts, failed}``;
    the caller commits ``db``. Raises ValueError(code) when unavailable."""
    plan = preview(db, item, rule)
    if not plan["available"]:
        raise ValueError(plan["unavailable_reason"])
    remedy = plan["remedy"]
    failed: List[Dict[str, Any]] = []
    if plan["kind"] == KIND_SETTING:
        for change in plan["changes"]:
            SETTINGS[remedy][1](change)
        entity = EntityType.SETTING
    else:
        dispatch = FLEET[remedy][1]
        by_id = {str(h.id): h for h in FLEET[remedy][0](db)}
        for host in plan["hosts"]:
            try:
                dispatch(db, by_id[host["id"]], user)
            except Exception as exc:  # pylint: disable=broad-except
                # One host the engine cannot plan for (unsupported OS) must not
                # stop the rest; it is reported with a reason CODE.  The
                # exception text goes to the log only -- it can carry internal
                # detail and must not reach the browser (CodeQL
                # py/stack-trace-exposure, 2026-10-11).
                logger.warning(
                    "Posture remedy %s failed for %s: %s", remedy, host["fqdn"], exc
                )
                failed.append({"fqdn": host["fqdn"], "reason": _failure_code(exc)})
        entity = EntityType.HOST
    db.add(
        models.PostureItemEvent(
            **scope,
            rule_key=item.rule_key,
            from_state=item.state,
            to_state=item.state,
            cause="remediation_requested",
            threat_model_version=threat_model_version,
            at=_now(),
        )
    )
    _audit(
        user,
        entity,
        f"Applied posture remedy {remedy} for {item.rule_key}",
        {
            "rule_key": item.rule_key,
            "remedy": remedy,
            "changes": plan["changes"],
            "hosts": [h["fqdn"] for h in plan["hosts"]],
            "failed": failed,
        },
    )
    return {
        "applied": True,
        "changes": plan["changes"],
        "hosts": plan["hosts"],
        "failed": failed,
    }
