"""
OS lifecycle action API (Phase 14.3) — "release-upgrade a host".

OSS orchestration: create a release-upgrade job via the Pro+ ``lifecycle_engine``
(method inference + pre-checks — the moat) and dispatch the upgrade command to the
agent through the EXISTING store-and-forward queue.  Because the command is a
``command`` message, 14.2 maintenance-window gating applies automatically; a job
with ``scheduled_at`` is additionally held by the queue until that time.

Gated behind the Professional ``OS_LIFECYCLE`` feature (defence in depth; the UI
hides it when unlicensed).
"""

from datetime import datetime

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
from backend.persistence.partitions import get_shared_db, get_tenant_db
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter(dependencies=[Depends(JWTBearer())])
queue_ops = QueueOperations()


class ReleaseUpgradeRequest(BaseModel):
    """Schedule a distro release-upgrade for a host.

    All fields optional: the engine infers the method from the host's OS and the
    target version from the shared lifecycle registry when not supplied.
    """

    to_version: str | None = None
    method: str | None = None
    scheduled_at: datetime | None = None  # honored by the queue + maint. windows


def _require_lifecycle_license() -> None:
    if not license_service.has_feature(FeatureCode.OS_LIFECYCLE):
        raise HTTPException(
            status_code=402,
            detail=_(
                "OS lifecycle management requires a SysManage Professional license."
            ),
        )


def _lifecycle_engine():
    """Return the loaded lifecycle_engine, or raise a clean 402/503."""
    if not license_service.has_module(ModuleCode.LIFECYCLE_ENGINE):
        raise HTTPException(
            status_code=402,
            detail=_(
                "OS lifecycle management requires a SysManage Professional license."
            ),
        )
    engine = module_loader.get_module("lifecycle_engine")
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail=_("The OS lifecycle module is not currently available."),
        )
    return engine


@router.post("/lifecycle/host/{host_id}/upgrade")
async def upgrade_host_release(
    host_id: str,
    body: ReleaseUpgradeRequest,
    tenant_db: Session = Depends(get_tenant_db),
    shared_db: Session = Depends(get_shared_db),
    current_user=Depends(get_current_user),
):
    """Create + dispatch a release-upgrade job for one host.

    The job (with method inference + pre-checks) is created by the engine against
    the tenant partition; the command is then enqueued through the same
    store-and-forward path every other host command uses — so agent delivery,
    maintenance-window gating (14.2), and ``scheduled_at`` deferral all apply
    unchanged.
    """
    _require_lifecycle_license()
    engine = _lifecycle_engine()

    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))

    # Create the job (moat: method inference + target-from-registry + pre-checks).
    try:
        job = engine._lifecycle_service.create_upgrade_job(
            host_id,
            tenant_db,
            models,
            lc_db=shared_db,
            to_version=body.to_version,
            method=body.method,
            scheduled_at=body.scheduled_at,
        )
    except Exception as exc:  # engine raises LifecycleServiceError on bad input
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Dispatch the upgrade command to the agent (tenant-scoped queue).
    command_message = create_command_message(
        command_type="os_release_upgrade",
        parameters={
            "job_id": job["id"],
            "method": job["method"],
            "to_version": job["to_version"],
            "from_version": job.get("from_version"),
        },
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

    # Audit trail lives on the main engine (server-global).
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
                f"Requested release-upgrade of host {host.fqdn} "
                f"to {job['to_version']} via {job['method']}"
            ),
            result=Result.SUCCESS,
        )

    return {"result": True, "job": job}
