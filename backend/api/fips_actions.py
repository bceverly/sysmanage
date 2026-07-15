"""
FIPS compliance-mode action API (Phase 14.4) — "enable/disable FIPS on a host"
and the fleet FIPS posture read.

Detection ("is FIPS on?") is OSS — every agent reports its posture and the
``handle_fips_compliance_update`` handler persists it on the host.  This module
covers the ENTERPRISE surface:

* enable/disable FIPS on a host — the Pro+ ``compliance_engine`` plans the change
  (method inference: ``pro enable fips`` on Ubuntu, ``fips-mode-setup`` on RHEL —
  the moat), and the command is dispatched to the agent through the EXISTING
  store-and-forward queue (so 14.2 maintenance-window gating applies).
* the fleet FIPS posture summary that backs the compliance dashboard.

Everything here is gated behind the Enterprise ``FIPS_MODE`` feature (defence in
depth; the UI hides it when unlicensed).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.features import FeatureCode, ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter(dependencies=[Depends(JWTBearer())])
queue_ops = QueueOperations()


class FipsChangeRequest(BaseModel):
    """Enable/disable FIPS on a host.  Method is inferred by the engine from the
    host's OS when not supplied; ``scheduled_at`` (if set) defers the change via
    the queue + maintenance windows."""

    method: str | None = None
    scheduled_at: str | None = None


def _require_fips_license() -> None:
    if not license_service.has_feature(FeatureCode.FIPS_MODE):
        raise HTTPException(
            status_code=402,
            detail=_("FIPS mode management requires a SysManage Enterprise license."),
        )


def _compliance_engine():
    """Return the loaded compliance_engine, or raise a clean 402/503."""
    if not license_service.has_module(ModuleCode.COMPLIANCE_ENGINE):
        raise HTTPException(
            status_code=402,
            detail=_("FIPS mode management requires a SysManage Enterprise license."),
        )
    engine = module_loader.get_module("compliance_engine")
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail=_("The compliance module is not currently available."),
        )
    return engine


def _change_fips(host_id: str, enable: bool, body, tenant_db, current_user):
    """Shared enable/disable orchestration (synchronous — no awaited I/O)."""
    _require_fips_license()
    engine = _compliance_engine()

    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))

    # Moat: infer the method from the host's OS + run pre-checks.
    try:
        plan = engine.plan_fips_change(
            {
                "platform": host.platform,
                "platform_release": host.platform_release,
                "fips_available": host.fips_available,
                "fips_enabled": host.fips_enabled,
                "fips_vendor": host.fips_vendor,
            },
            enable=enable,
            method=body.method,
        )
    except Exception as exc:  # engine raises on unsupported OS / bad state
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    command_type = "fips_enable" if enable else "fips_disable"
    command_message = create_command_message(
        command_type=command_type,
        parameters=plan.get("parameters", {}),
    )
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=tenant_db,
        scheduled_at=body.scheduled_at,
    )
    tenant_db.commit()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            username=current_user,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=(
                f"Requested {'enable' if enable else 'disable'} of FIPS mode on "
                f"host {host.fqdn} via {plan.get('method')}"
            ),
            result=Result.SUCCESS,
        )

    return {"result": True, "plan": plan}


@router.post("/fips/host/{host_id}/enable")
async def enable_fips(
    host_id: str,
    body: FipsChangeRequest,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(get_current_user),
):
    """Enable FIPS mode on a host (Enterprise)."""
    return _change_fips(host_id, True, body, tenant_db, current_user)


@router.post("/fips/host/{host_id}/disable")
async def disable_fips(
    host_id: str,
    body: FipsChangeRequest,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(get_current_user),
):
    """Disable FIPS mode on a host (Enterprise)."""
    return _change_fips(host_id, False, body, tenant_db, current_user)


@router.get("/fips/host/{host_id}")
async def host_fips_status(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(get_current_user),  # noqa: ARG001
):
    """Per-host FIPS posture that backs the host-detail FIPS card (Enterprise).

    Detection is OSS (the agent reports it); the card + the enable/disable
    controls it drives are the Enterprise surface, so the read is gated too.
    """
    _require_fips_license()
    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    return {
        "host_id": str(host.id),
        "fqdn": host.fqdn,
        "platform": host.platform,
        "platform_release": host.platform_release,
        "fips_status": host.fips_status or "not_applicable",
        "fips_enabled": host.fips_enabled,
        "fips_available": host.fips_available,
        "fips_kernel_enforced": host.fips_kernel_enforced,
        "fips_vendor": host.fips_vendor,
        "fips_package_version": host.fips_package_version,
        "fips_updated_at": (
            host.fips_updated_at.isoformat() if host.fips_updated_at else None
        ),
    }


@router.get("/fips/fleet")
async def fleet_fips_posture(
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(get_current_user),  # noqa: ARG001
):
    """Fleet-wide FIPS posture summary that backs the compliance dashboard.

    Reads the per-host status the agents already report (OSS data); the summary
    view itself is the Enterprise surface, so it is gated.
    """
    _require_fips_license()
    hosts = tenant_db.query(models.Host).filter(models.Host.active.is_(True)).all()
    counts = {"enabled": 0, "available": 0, "disabled": 0, "not_applicable": 0}
    per_host = []
    for host in hosts:
        status = host.fips_status or "not_applicable"
        counts[status] = counts.get(status, 0) + 1
        per_host.append(
            {
                "host_id": str(host.id),
                "fqdn": host.fqdn,
                "platform": host.platform,
                "fips_status": status,
                "fips_enabled": host.fips_enabled,
                "fips_available": host.fips_available,
                "fips_kernel_enforced": host.fips_kernel_enforced,
                "fips_vendor": host.fips_vendor,
                "fips_updated_at": (
                    host.fips_updated_at.isoformat() if host.fips_updated_at else None
                ),
            }
        )
    return {"counts": counts, "total": len(hosts), "hosts": per_host}
