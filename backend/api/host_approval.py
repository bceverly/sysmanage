"""
This module houses host approval/rejection and OS update request API routes.
"""

import logging
from datetime import datetime, timezone

from cryptography import x509
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import validate_host_approval_status
from backend.api.error_constants import error_host_not_found
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.models import HostChild
from backend.persistence.partitions import get_request_engine
from backend.persistence.tenant_context import get_active_tenant
from backend.security.certificate_manager import certificate_manager
from backend.security.roles import SecurityRoles
from backend.services.audit_service import AuditService, EntityType
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
async def approve_host(  # NOSONAR
    host_id: str, current_user=Depends(require_authenticated_user)
):  # pylint: disable=duplicate-code
    """
    Approve a pending host registration
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global).  A host is bound to its tenant at
    # registration (via enrollment token) before approval, so the approval data
    # routes to the active tenant's engine; in collapsed/single-tenant mode this
    # is the same single application engine.
    if not current_user.has_role(SecurityRoles.APPROVE_HOST_REGISTRATION):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: APPROVE_HOST_REGISTRATION role required"),
        )

    # Capture the active tenant in the request's async context (the ContextVar
    # is resolved by get_request_engine via the middleware-bound value).
    tenant_id = get_active_tenant()
    bind = db.get_engine() if tenant_id is None else get_request_engine(tenant_id)
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=bind
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=error_host_not_found())

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

        # Phase 10.4.4 — auto-apply default mirror assignments for the
        # newly-approved host.  Best-effort; any failure is logged and
        # swallowed so approval itself never breaks because of a
        # mirror engine quirk.
        try:
            from backend.api.repository_mirroring import (
                apply_default_mirrors_for_new_host,
            )

            apply_default_mirrors_for_new_host(str(host.id))
        except (
            Exception
        ) as exc:  # pylint: disable=broad-except  # nosec B110 - mirror auto-apply is best-effort
            logger.warning(
                "Default-mirror auto-apply failed for approved host %s: %s",
                host.fqdn,
                exc,
            )

        # Check if this host was created as a child host and link them
        try:
            # Look for HostChild records that match this host's hostname
            # and haven't been linked yet (child_host_id is null)
            # The hostname in HostChild might be short (e.g., "afedora") or FQDN
            # while host.fqdn is always FQDN (e.g., "afedora.theeverlys.com")
            # So we check if FQDN starts with the stored hostname
            host_short_name = host.fqdn.split(".")[0] if host.fqdn else None

            matching_child = None
            if host_short_name:
                # First try exact FQDN match
                # Match both "running" and "creating" status - child may register
                # before parent agent reports it as running
                matching_child = (
                    session.query(HostChild)
                    .filter(
                        HostChild.hostname == host.fqdn,
                        HostChild.child_host_id.is_(None),
                        HostChild.status.in_(["running", "creating"]),
                    )
                    .first()
                )

                # If no exact match, try matching short hostname
                if not matching_child:
                    matching_child = (
                        session.query(HostChild)
                        .filter(
                            HostChild.hostname == host_short_name,
                            HostChild.child_host_id.is_(None),
                            HostChild.status.in_(["running", "creating"]),
                        )
                        .first()
                    )

                # If still no match, check if host.fqdn starts with HostChild.hostname
                if not matching_child:
                    # Get all unlinked child hosts (running or creating) and check prefix match
                    unlinked_children = (
                        session.query(HostChild)
                        .filter(
                            HostChild.child_host_id.is_(None),
                            HostChild.status.in_(["running", "creating"]),
                            HostChild.hostname.isnot(None),
                        )
                        .all()
                    )
                    for child in unlinked_children:
                        if host.fqdn.startswith(child.hostname + "."):
                            matching_child = child
                            break

                # Fallback: If hostname is NULL, try matching child_name to short hostname
                # This handles cases where VMs were reported by agent before
                # metadata was available (e.g., bhyve VMs discovered by listing)
                if not matching_child:
                    matching_child = (
                        session.query(HostChild)
                        .filter(
                            HostChild.child_name == host_short_name,
                            HostChild.child_host_id.is_(None),
                            HostChild.status.in_(["running", "creating"]),
                            HostChild.hostname.is_(
                                None
                            ),  # Only match if hostname is NULL
                        )
                        .first()
                    )
                    if matching_child:
                        # Update the hostname field while we're at it
                        matching_child.hostname = host.fqdn
                        logger.info(
                            "Matched by child_name '%s', updated hostname to '%s'",
                            host_short_name,
                            host.fqdn,
                        )

            if matching_child:
                # Link the child host to the approved host
                matching_child.child_host_id = host.id
                matching_child.installed_at = datetime.now(timezone.utc).replace(
                    tzinfo=None
                )
                # Update status from "creating" to "running" if needed
                if matching_child.status == "creating":
                    matching_child.status = "running"
                # Also set parent_host_id on the host record for easier filtering
                host.parent_host_id = matching_child.parent_host_id
                session.commit()
                logger.info(
                    "Linked child host %s to approved host %s (%s), parent=%s",
                    matching_child.id,
                    host.id,
                    host.fqdn,
                    matching_child.parent_host_id,
                )
        except Exception as e:
            # Don't fail the approval process if we can't link child host
            logger.exception(
                "Error linking child host for %s (%s): %s",
                host.id,
                host.fqdn,
                e,
            )

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
            logger.exception(
                "Error applying enabled package managers to %s (%s): %s",
                host.id,
                host.fqdn,
                e,
            )

        # Audit log host approval
        AuditService.log_update(
            db=session,
            user_id=current_user.id,
            username=current_user.userid,
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
    host_id: str, current_user=Depends(require_authenticated_user)
):  # pylint: disable=duplicate-code
    """
    Reject a pending host registration
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global).  The host's approval data is tenant-
    # scoped (bound at registration), so it routes to the active tenant's engine;
    # collapsed/single-tenant mode keeps using the single application engine.
    tenant_id = get_active_tenant()
    bind = db.get_engine() if tenant_id is None else get_request_engine(tenant_id)
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=bind
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=error_host_not_found())

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
            user_id=current_user.id,
            username=current_user.userid,
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
    # Operator-facing: the host + queue data is tenant-scoped, so route to the
    # active tenant's engine (collapsed/single-tenant mode keeps the single
    # application engine).
    tenant_id = get_active_tenant()
    bind = db.get_engine() if tenant_id is None else get_request_engine(tenant_id)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=bind)

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=error_host_not_found())

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
    # Operator-facing: the host + queue data is tenant-scoped, so route to the
    # active tenant's engine (collapsed/single-tenant mode keeps the single
    # application engine).
    tenant_id = get_active_tenant()
    bind = db.get_engine() if tenant_id is None else get_request_engine(tenant_id)
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=bind
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=error_host_not_found())

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
