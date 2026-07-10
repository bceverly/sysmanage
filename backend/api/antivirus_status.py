"""
This module houses the API routes for antivirus status management in SysManage.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import (
    error_host_not_found,
    error_invalid_host_id,
    error_permission_denied,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as persistence_db
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import av_plan_builder
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import sanitize_log
from backend.websocket.messages import CommandType, Message, MessageType


def _host_info_for_av_planner(host: models.Host) -> dict:
    """Pack a Host's OS fields into the dict the AV plan builder expects."""
    return {
        "platform": host.platform,
        "platform_release": host.platform_release,
        "platform_version": host.platform_version,
    }


from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

router = APIRouter()
queue_ops = QueueOperations()


class AntivirusStatusResponse(BaseModel):
    """Response model for antivirus status."""

    id: str
    host_id: str
    software_name: Optional[str] = None
    install_path: Optional[str] = None
    version: Optional[str] = None
    enabled: Optional[bool] = None
    last_updated: datetime

    @validator("id", "host_id", pre=True)
    def convert_uuid_to_string(
        cls, value
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    @validator("last_updated", pre=True)
    def add_utc_timezone(
        cls, value
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
        """Add UTC timezone to naive datetime."""
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


@router.get(
    "/hosts/{host_id}/antivirus-status",
    response_model=Optional[AntivirusStatusResponse],
)
async def get_antivirus_status(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
):
    """Get antivirus status for a specific host."""
    try:
        # Convert host_id to UUID
        try:
            host_uuid = uuid.UUID(host_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=error_invalid_host_id(),
            ) from e

        # Check if host exists
        host = db.query(models.Host).filter(models.Host.id == host_uuid).first()
        if not host:
            raise HTTPException(
                status_code=404,
                detail=error_host_not_found(),
            )

        # Get antivirus status
        status = (
            db.query(models.AntivirusStatus)
            .filter(models.AntivirusStatus.host_id == host_uuid)
            .first()
        )

        if not status:
            return None

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Error getting antivirus status for host %s: %s", sanitize_log(host_id), e
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve antivirus status: %s") % str(e),
        ) from e


class AntivirusDeployRequest(BaseModel):
    """Request model for deploying antivirus to hosts."""

    host_ids: List[str]


class AntivirusDeployResponse(BaseModel):
    """Response model for antivirus deployment."""

    success_count: int
    failed_hosts: List[dict]
    message: str


@router.post("/deploy", response_model=AntivirusDeployResponse)
async def deploy_antivirus(  # NOSONAR
    deploy_request: AntivirusDeployRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Deploy antivirus to one or more hosts."""
    # Authorization is resolved on the MAIN engine by
    # require_authenticated_user (user/role data is server-global); host and
    # antivirus-default data route to the tenant engine via ``db_session``.
    if not current_user.has_role(SecurityRoles.DEPLOY_ANTIVIRUS):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: DEPLOY_ANTIVIRUS role required"),
        )
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=persistence_db.get_engine()
    )

    # Process each host
    success_count = 0
    failed_hosts = []

    # Host and antivirus-default data live in the tenant database (``session``
    # below = ``db_session``); the audit trail stays on the main engine
    # (``audit_session``).
    with session_local() as audit_session:
        session = db_session
        # Bulk-fetch all hosts and all AntivirusDefaults upfront in two
        # queries instead of 2 per host (flagged in the Phase 6 N+1
        # audit).  AntivirusDefault is a tiny lookup table — load all
        # rows; many hosts share an OS so per-host lookups duplicate
        # work.
        valid_uuids = []
        invalid_ids = []
        for hid in deploy_request.host_ids:
            try:
                valid_uuids.append(uuid.UUID(hid))
            except ValueError:
                invalid_ids.append(hid)
        hosts_by_id = {
            h.id: h
            for h in (
                session.query(models.Host).filter(models.Host.id.in_(valid_uuids)).all()
                if valid_uuids
                else []
            )
        }
        defaults_by_os = {
            d.os_name: d for d in session.query(models.AntivirusDefault).all()
        }

        for host_id_str in deploy_request.host_ids:
            try:
                if host_id_str in invalid_ids:
                    failed_hosts.append(
                        {
                            "host_id": host_id_str,
                            "hostname": "Unknown",
                            "reason": _("Invalid host ID format"),
                        }
                    )
                    continue

                host_id = uuid.UUID(host_id_str)
                host = hosts_by_id.get(host_id)
                if not host:
                    failed_hosts.append(
                        {
                            "host_id": host_id_str,
                            "hostname": "Unknown",
                            "reason": _("Host not found"),
                        }
                    )
                    continue

                # Get OS name (platform_release or platform)
                # For macOS, use platform directly since platform_release contains version codenames
                # For BSD systems, platform_release might be just "7.7", so fall back to platform
                if host.platform == "macOS":
                    os_name_raw = "macOS"
                else:
                    os_name_raw = host.platform_release or host.platform

                    # If platform_release doesn't start with a letter (e.g., "7.7" for OpenBSD), use platform instead
                    if os_name_raw and not re.match(r"^[A-Za-z]", os_name_raw):
                        os_name_raw = host.platform or os_name_raw

                if not os_name_raw:
                    failed_hosts.append(
                        {
                            "host_id": host_id_str,
                            "hostname": host.fqdn,
                            "reason": _("Unable to determine host operating system"),
                        }
                    )
                    continue

                # Extract base OS name without version (e.g., "Ubuntu 25.04" -> "Ubuntu")
                # For macOS, we already have the base name
                if host.platform == "macOS":
                    os_name = "macOS"
                else:
                    match = re.match(r"^([A-Za-z]+)", os_name_raw)
                    os_name = match.group(1) if match else os_name_raw

                # Lookup antivirus default in the prefetched dict (built
                # at the top of this with-block).
                antivirus_default = defaults_by_os.get(os_name)

                if not antivirus_default or not antivirus_default.antivirus_package:
                    failed_hosts.append(
                        {
                            "host_id": host_id_str,
                            "hostname": host.fqdn,
                            "reason": _("No antivirus default configured for OS: %s")
                            % os_name,
                        }
                    )
                    continue

                # Build a declarative deploy plan; agent runs it via
                # apply_deployment_plan.
                deploy_plan = av_plan_builder.build_deploy_plan(
                    _host_info_for_av_planner(host),
                    antivirus_default.antivirus_package,
                )
                command_message = Message(
                    message_type=MessageType.COMMAND,
                    data={
                        "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
                        "parameters": {"plan": deploy_plan},
                    },
                )

                # Send command to agent via WebSocket/queue
                queue_ops.enqueue_message(
                    message_type="command",
                    message_data=command_message.to_dict(),
                    direction=QueueDirection.OUTBOUND,
                    host_id=str(host_id),
                    db=session,
                )

                # Audit log the antivirus deployment (main engine)
                AuditService.log(
                    db=audit_session,
                    user_id=current_user.id,
                    username=current_user.userid,
                    action_type=ActionType.EXECUTE,
                    entity_type=EntityType.HOST,
                    entity_id=str(host_id),
                    entity_name=host.fqdn,
                    description=f"Requested antivirus deployment for host {host.fqdn}",
                    result=Result.SUCCESS,
                    details={"antivirus_package": antivirus_default.antivirus_package},
                )

                success_count += 1
                logger.info(
                    "Antivirus deployment initiated for host %s (%s) with package %s",
                    host.fqdn,
                    sanitize_log(host_id_str),
                    antivirus_default.antivirus_package,
                )

            except Exception as e:
                logger.exception(
                    "Error deploying antivirus to host %s: %s",
                    sanitize_log(host_id_str),
                    e,
                )
                failed_hosts.append(
                    {"host_id": host_id_str, "hostname": "Unknown", "reason": str(e)}
                )

        # Commit the session to persist all queued messages
        session.commit()

    # Generate response message
    if success_count == len(deploy_request.host_ids):
        message = _("Antivirus deployment initiated for all %d hosts") % success_count
    elif success_count > 0:
        message = _(
            "Antivirus deployment initiated for %(success_count)d of %(total_count)d hosts"
        ) % {
            "success_count": success_count,
            "total_count": len(deploy_request.host_ids),
        }
    else:
        message = _("Antivirus deployment failed for all hosts")

    return AntivirusDeployResponse(
        success_count=success_count, failed_hosts=failed_hosts, message=message
    )


@router.post(
    "/hosts/{host_id}/antivirus/enable",
    dependencies=[Depends(JWTBearer())],
)
async def enable_antivirus(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Enable antivirus on a specific host."""
    # Authorization is resolved on the MAIN engine by
    # require_authenticated_user; host/queue data routes to the tenant engine
    # via ``db``, and the audit trail stays on the main engine.
    if not current_user.has_role(SecurityRoles.ENABLE_ANTIVIRUS):
        raise HTTPException(status_code=403, detail=error_permission_denied())
    audit_session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=persistence_db.get_engine()
    )

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    plan = av_plan_builder.build_enable_plan(_host_info_for_av_planner(host))
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
            "parameters": {"plan": plan},
            "timeout": 300,
        },
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )

    # Commit the tenant session to persist the queued message.
    db.commit()

    # Audit log the antivirus enable command (main engine).
    with audit_session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=f"Requested antivirus enable for host {host.fqdn}",
            result=Result.SUCCESS,
        )
        audit_session.commit()

    logger.info("Antivirus enable command sent to host %s", host.fqdn)
    return {"message": _("Antivirus enable command sent successfully")}


@router.post(
    "/hosts/{host_id}/antivirus/disable",
    dependencies=[Depends(JWTBearer())],
)
async def disable_antivirus(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Disable antivirus on a specific host."""
    # Authorization is resolved on the MAIN engine by
    # require_authenticated_user; host/queue data routes to the tenant engine
    # via ``db``, and the audit trail stays on the main engine.
    if not current_user.has_role(SecurityRoles.DISABLE_ANTIVIRUS):
        raise HTTPException(status_code=403, detail=error_permission_denied())
    audit_session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=persistence_db.get_engine()
    )

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    plan = av_plan_builder.build_disable_plan(_host_info_for_av_planner(host))
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
            "parameters": {"plan": plan},
            "timeout": 300,
        },
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )

    # Commit the tenant session to persist the queued message.
    db.commit()

    # Audit log the antivirus disable command (main engine).
    with audit_session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=f"Requested antivirus disable for host {host.fqdn}",
            result=Result.SUCCESS,
        )
        audit_session.commit()

    logger.info("Antivirus disable command sent to host %s", host.fqdn)
    return {"message": _("Antivirus disable command sent successfully")}


@router.post(
    "/hosts/{host_id}/antivirus/remove",
    dependencies=[Depends(JWTBearer())],
)
async def remove_antivirus(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Remove antivirus from a specific host."""
    try:
        # Authorization is resolved on the MAIN engine by
        # require_authenticated_user; host/queue data routes to the tenant
        # engine via ``db``, and the audit trail stays on the main engine.
        logger.info(
            "remove_antivirus called for host_id=%s by user=%s",
            sanitize_log(host_id),
            sanitize_log(current_user.userid),
        )
        if not current_user.has_role(SecurityRoles.REMOVE_ANTIVIRUS):
            logger.error(
                "User %s lacks REMOVE_ANTIVIRUS role",
                sanitize_log(current_user.userid),
            )
            raise HTTPException(status_code=403, detail=error_permission_denied())
        audit_session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=persistence_db.get_engine()
        )

        # Get host
        host = db.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            logger.error("Host not found: %s", sanitize_log(host_id))
            raise HTTPException(status_code=404, detail=error_host_not_found())

        plan = av_plan_builder.build_remove_plan(_host_info_for_av_planner(host))
        message = Message(
            message_type=MessageType.COMMAND,
            data={
                "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
                "parameters": {"plan": plan},
                "timeout": 300,
            },
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=message.to_dict(),
            direction=QueueDirection.OUTBOUND,
            host_id=str(host.id),
            db=db,
        )

        # Commit the tenant session to persist the queued message.
        db.commit()

        # Audit log the antivirus remove command (main engine).
        with audit_session_local() as audit_session:
            AuditService.log(
                db=audit_session,
                user_id=current_user.id,
                username=current_user.userid,
                action_type=ActionType.EXECUTE,
                entity_type=EntityType.HOST,
                entity_id=str(host.id),
                entity_name=host.fqdn,
                description=f"Requested antivirus removal for host {host.fqdn}",
                result=Result.SUCCESS,
            )
            audit_session.commit()

        logger.info("Antivirus remove command sent to host %s", host.fqdn)
        return {"message": _("Antivirus remove command sent successfully")}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in remove_antivirus: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {str(e)}"
        ) from e


class AntivirusCoverageResponse(BaseModel):
    """Response model for antivirus coverage statistics."""

    total_hosts: int
    hosts_with_antivirus: int
    hosts_without_antivirus: int
    coverage_percentage: float


@router.get(
    "/antivirus-coverage",
    response_model=AntivirusCoverageResponse,
    dependencies=[Depends(JWTBearer())],
)
async def get_antivirus_coverage(db: Session = Depends(get_tenant_db)):
    """Get antivirus coverage statistics across all registered hosts."""
    try:
        total_hosts = db.query(models.Host).count()

        if total_hosts == 0:
            return AntivirusCoverageResponse(
                total_hosts=0,
                hosts_with_antivirus=0,
                hosts_without_antivirus=0,
                coverage_percentage=0.0,
            )

        # Bulk-fetch instead of one query per host (the previous loop
        # issued 2N queries — flagged in the Phase 6 audit).  Two
        # queries total now, regardless of fleet size.
        opensource_host_ids = {
            row[0]
            for row in db.query(models.AntivirusStatus.host_id)
            .filter(models.AntivirusStatus.enabled.is_(True))
            .all()
        }
        commercial_host_ids = {
            row[0]
            for row in db.query(models.CommercialAntivirusStatus.host_id)
            .filter(models.CommercialAntivirusStatus.antivirus_enabled.is_(True))
            .all()
        }
        hosts_with_antivirus = len(opensource_host_ids | commercial_host_ids)
        hosts_without_antivirus = total_hosts - hosts_with_antivirus
        coverage_percentage = (
            (hosts_with_antivirus / total_hosts * 100) if total_hosts > 0 else 0.0
        )

        return AntivirusCoverageResponse(
            total_hosts=total_hosts,
            hosts_with_antivirus=hosts_with_antivirus,
            hosts_without_antivirus=hosts_without_antivirus,
            coverage_percentage=round(coverage_percentage, 2),
        )

    except Exception as e:
        logger.exception("Error getting antivirus coverage statistics: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve antivirus coverage: %s") % str(e),
        ) from e
