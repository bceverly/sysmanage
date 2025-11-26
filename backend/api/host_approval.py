"""
This module houses host approval/rejection and OS update request API routes.
"""

import logging
from datetime import datetime, timezone

from cryptography import x509
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.certificate_manager import certificate_manager
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import (
    create_command_message,
    create_host_approved_message,
)
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
logger = logging.getLogger(__name__)
queue_ops = QueueOperations()


@router.put("/host/{host_id}/approve", dependencies=[Depends(JWTBearer())])
async def approve_host(
    host_id: str, current_user: str = Depends(get_current_user)
):  # pylint: disable=duplicate-code
    """
    Approve a pending host registration
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to approve hosts
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for APPROVE_HOST_REGISTRATION role
        if not user.has_role(SecurityRoles.APPROVE_HOST_REGISTRATION):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: APPROVE_HOST_REGISTRATION role required"),
            )
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        if host.approval_status != "pending":
            raise HTTPException(
                status_code=400, detail=_("Host is not in pending status")
            )

        # Generate client certificate for the approved host
        cert_pem, _unused = certificate_manager.generate_client_certificate(
            host.fqdn, host.id
        )

        # Store certificate information in host record
        host.client_certificate = cert_pem.decode("utf-8")
        host.certificate_issued_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Extract serial number for tracking

        cert = x509.load_pem_x509_certificate(cert_pem)
        host.certificate_serial = str(cert.serial_number)

        # Update approval status
        host.approval_status = "approved"
        host.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()

        # Apply default repositories for this host's operating system
        try:
            from backend.api.default_repositories import (
                apply_default_repositories_to_host,
            )

            await apply_default_repositories_to_host(session, host)
        except Exception as e:
            # Don't fail the approval process if we can't apply default repos
            print(
                f"DEBUG: Error applying default repositories to {host.id} ({host.fqdn}): {e}",
                flush=True,
            )

        # Apply enabled package managers for this host's operating system
        try:
            import json

            # Get the distribution from os_details
            os_details = json.loads(host.os_details) if host.os_details else {}
            distribution = os_details.get("distribution", "")

            if distribution and host.is_agent_privileged:
                # Get all enabled package managers for this OS
                enabled_pms = (
                    session.query(models.EnabledPackageManager)
                    .filter(models.EnabledPackageManager.os_name == distribution)
                    .all()
                )

                if enabled_pms:
                    for pm in enabled_pms:
                        command_message = create_command_message(
                            command_type="enable_package_manager",
                            parameters={
                                "package_manager": pm.package_manager,
                                "os_name": pm.os_name,
                            },
                        )
                        queue_ops.enqueue_message(
                            message_type="command",
                            message_data=command_message,
                            direction=QueueDirection.OUTBOUND,
                            host_id=str(host.id),
                            db=session,
                        )
                    session.commit()
                    logger.info(
                        "Queued %d enabled package manager commands for newly approved host %s (%s)",
                        len(enabled_pms),
                        host.fqdn,
                        distribution,
                    )
        except Exception as e:
            # Don't fail the approval process if we can't apply enabled PMs
            logger.error(
                "Error applying enabled package managers to %s (%s): %s",
                host.id,
                host.fqdn,
                e,
            )

        # Audit log host approval
        AuditService.log_update(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
        )

        # Send host approval notification to the agent via WebSocket
        try:
            approval_message = create_host_approved_message(
                host_id=str(host.id),
                host_token=host.host_token,
                approval_status="approved",
                certificate=host.client_certificate,
            )

            # Enqueue the message to be sent to the agent
            queue_ops.enqueue_message(
                message_type="host_approved",
                message_data=approval_message,
                direction=QueueDirection.OUTBOUND,
                host_id=str(host.id),
                db=session,
            )
            # Commit the session to persist the queued message
            session.commit()
            print(
                f"DEBUG: Enqueued host approval notification for host {host.id} ({host.fqdn})",
                flush=True,
            )
        except Exception as e:
            # Don't fail the approval process if we can't enqueue the notification
            print(
                f"DEBUG: Error enqueuing host approval notification to {host.id} ({host.fqdn}): {e}",
                flush=True,
            )

        ret_host = models.Host(
            id=host.id,
            active=host.active,
            fqdn=host.fqdn,
            ipv4=host.ipv4,
            ipv6=host.ipv6,
            status=host.status,
            approval_status=host.approval_status,
            last_access=host.last_access,
        )

        return ret_host


@router.put("/host/{host_id}/reject", dependencies=[Depends(JWTBearer())])
async def reject_host(
    host_id: str, current_user: str = Depends(get_current_user)
):  # pylint: disable=duplicate-code
    """
    Reject a pending host registration
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get the user object for audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        if host.approval_status != "pending":
            raise HTTPException(
                status_code=400, detail=_("Host is not in pending status")
            )

        # Update approval status
        host.approval_status = "rejected"
        host.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()

        # Audit log host rejection
        AuditService.log_update(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
        )

        ret_host = models.Host(
            id=host.id,
            active=host.active,
            fqdn=host.fqdn,
            ipv4=host.ipv4,
            ipv6=host.ipv6,
            status=host.status,
            approval_status=host.approval_status,
            last_access=host.last_access,
        )

        return ret_host


@router.post("/host/{host_id}/request-os-update", dependencies=[Depends(JWTBearer())])
async def request_os_version_update(host_id: str):
    """
    Request an agent to update its OS version information.
    This sends a message via WebSocket to the agent requesting fresh OS data.
    """
    # Get a fresh session to avoid transaction warnings
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        validate_host_approval_status(host)

        # Create command message for OS version update request
        command_message = create_command_message(
            command_type="update_os_version", parameters={}
        )

        # Enqueue command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )
        # Commit the session to persist the queued message
        session.commit()

        return {"result": True, "message": _("OS version update requested")}


@router.post(
    "/host/{host_id}/request-updates-check", dependencies=[Depends(JWTBearer())]
)
async def request_updates_check(host_id: str):
    """
    Request an agent to check for available updates.
    This sends a message via WebSocket to the agent requesting an update check.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        validate_host_approval_status(host)

        # Create command message for updates check request
        command_message = create_command_message(
            command_type="check_updates", parameters={}
        )

        # Enqueue command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )
        # Commit the session to persist the queued message
        session.commit()

        return {"result": True, "message": _("Updates check requested")}
