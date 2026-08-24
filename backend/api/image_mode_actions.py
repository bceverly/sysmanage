# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Image-mode host action API (Phase 17.3) — "stage / apply / rollback an image".

OSS orchestration for image-mode (bootc / rpm-ostree / OSTree) hosts: the Pro+
``image_mode_engine`` (Enterprise) builds the stage/apply/rollback command plan
(the moat), and this router dispatches it to the agent through the EXISTING
store-and-forward queue via the generic ``apply_deployment_plan`` handler — the
same path the 17.1/17.2 repoint plans use, so agent delivery and maintenance-
window gating (14.2) apply unchanged.

Detection ("is this an image-mode host + which deployment is booted?") is OSS
and rides ``os_version_update``; only the ACTIONS below are Enterprise-gated
(402 when ``image_mode_engine`` is not loaded).  After a no-reboot *stage* we
also enqueue ``update_os_version`` so the newly staged deployment shows up
promptly; *apply* / *rollback* reboot, so their boot-time ``os_version_update``
reports the settled state.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
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


class StageImageRequest(BaseModel):
    """Stage a new image deployment. ``target_ref`` rebases onto a different
    image (bootc only); omit it to stage the newest of the current image."""

    target_ref: Optional[str] = None
    bypass_update_driver: bool = True


class ApplyImageRequest(BaseModel):
    """Apply the staged deployment.

    ``bypass_update_driver`` defaults to True because Fedora CoreOS hands
    updates to Zincati, and rpm-ostree then REFUSES to act -- "Updates and
    deployments are driven by Zincati", exit 1 -- so without the bypass
    SysManage cannot update FCOS at all (measured on a real host 2026-08-24).
    Set it False to leave the host's own update driver in charge; the request
    then fails on such a host, which is the honest outcome rather than a
    silent no-op.  Ignored on bootc, and never applied to rollback, which
    does not accept the flag.
    """

    bypass_update_driver: bool = True


def _image_mode_engine():
    """Return the loaded image_mode_engine, or raise a clean 402 (Enterprise)."""
    engine = module_loader.get_module("image_mode_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Image-mode host management requires a SysManage Enterprise "
                "license. Please upgrade to access this feature."
            ),
        )
    return engine


def _image_mode_host_or_400(tenant_db: Session, host_id: str):
    """Fetch the host and require it be a detected image-mode host."""
    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    if not host.is_image_mode or not host.image_backend:
        raise HTTPException(
            status_code=400,
            detail=_("This host is not an image-mode (bootc / rpm-ostree) host."),
        )
    return host


def _build_plan(
    engine,
    action: str,
    backend: str,
    target_ref: Optional[str],
    bypass_update_driver: bool = True,
):
    """Build the stage/apply/rollback command plan for a backend, → 400 on bad input."""
    err = getattr(engine, "ImageModeError", Exception)
    try:
        if action == "stage":
            return engine.build_image_stage_plan(
                backend, target_ref, bypass_update_driver
            )
        if action == "apply":
            return engine.build_image_apply_plan(backend, bypass_update_driver)
        # Rollback takes no bypass flag: rpm-ostree rejects it outright
        # ("Unknown option --bypass-driver"), so passing it would break the
        # one image-mode path that already worked.
        return engine.build_image_rollback_plan(backend)
    except err as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _dispatch(
    action: str,
    host_id: str,
    tenant_db: Session,
    current_user,
    target_ref: Optional[str] = None,
    bypass_update_driver: bool = True,
):
    """Shared stage/apply/rollback flow: gate → build plan → enqueue → audit."""
    engine = _image_mode_engine()
    host = _image_mode_host_or_400(tenant_db, host_id)
    plan = _build_plan(
        engine, action, host.image_backend, target_ref, bypass_update_driver
    )

    # Dispatch the plan through the generic apply_deployment_plan handler.
    command_message = create_command_message(
        command_type="apply_deployment_plan",
        parameters={"plan": plan},
    )
    message_id = queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=tenant_db,
    )

    # A no-reboot stage won't otherwise re-report; force a prompt os refresh so
    # the newly staged deployment appears. (apply/rollback reboot → boot report.)
    if action == "stage":
        queue_ops.enqueue_message(
            message_type="command",
            message_data=create_command_message(
                command_type="update_os_version", parameters={}
            ),
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=tenant_db,
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
                f"Requested image-mode {action} on host {host.fqdn} "
                f"({host.image_backend})"
            ),
            result=Result.SUCCESS,
        )

    return {"result": True, "action": action, "message_id": message_id}


@router.post("/image-mode/host/{host_id}/stage")
async def stage_host_image(
    host_id: str,
    body: StageImageRequest = StageImageRequest(),
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(get_current_user),
):
    """Fetch + stage a new image deployment WITHOUT rebooting."""
    return _dispatch(
        "stage",
        host_id,
        tenant_db,
        current_user,
        body.target_ref,
        body.bypass_update_driver,
    )


@router.post("/image-mode/host/{host_id}/apply")
async def apply_host_image(
    host_id: str,
    body: ApplyImageRequest = ApplyImageRequest(),
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(get_current_user),
):
    """Apply the staged deployment — boot into the new image."""
    return _dispatch(
        "apply",
        host_id,
        tenant_db,
        current_user,
        None,
        body.bypass_update_driver,
    )


@router.post("/image-mode/host/{host_id}/rollback")
async def rollback_host_image(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(get_current_user),
):
    """Roll back to the prior deployment and reboot into it."""
    return _dispatch("rollback", host_id, tenant_db, current_user)
