"""
Package installation and uninstallation operations.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from backend.api.packages_models import (
    PackageInstallRequest,
    PackageInstallResponse,
    PackageUninstallRequest,
    PackageUninstallResponse,
)
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.models import Host, InstallationPackage, InstallationRequest
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    server_queue_manager,
)


async def install_packages_operation(  # NOSONAR
    host_id: str,
    request: PackageInstallRequest,
    db: Session,
    current_user: str,
) -> PackageInstallResponse:
    """
    Queue package installation for a specific host using UUID-based grouping.

    Creates a single installation request with multiple packages grouped under one UUID.
    The agent will receive this UUID and return it when reporting completion.

    Phase 13.1: this is a helper (not a FastAPI endpoint) invoked by the
    ``install_packages`` route in ``packages.py``.  The caller passes the
    TENANT-scoped ``db`` session (used for the install-request DATA) plus the
    ``current_user`` userid string.  User identities / roles are server-global
    and live on the MAIN engine, so authorization is resolved on an explicit
    main-engine session below — never on the tenant ``db``.  The audit trail is
    also server-global and is written on a separate main-engine session.
    """
    try:
        # Resolve authorization on the MAIN engine — user/role data is
        # server-global and is NOT present in the tenant ``db``.
        main_session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with main_session_local() as session:
            user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.ADD_PACKAGE):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: ADD_PACKAGE role required"),
                )

            # Capture the user id while the session is still open; the audit
            # log (written on a fresh main-engine session) needs it later.
            audit_user_id = user.id

        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Validate that packages are not empty
        if not request.package_names:
            raise HTTPException(
                status_code=400,
                detail=_("No packages specified for installation"),
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Generate a single UUID for this entire installation request
        request_id = str(uuid.uuid4())

        # Create the primary installation request record
        installation_request = InstallationRequest(
            id=request_id,
            host_id=host_id,
            requested_by=request.requested_by,
            requested_at=now,
            status="pending",
            operation_type="install",
            created_at=now,
            updated_at=now,
        )
        db.add(installation_request)

        # Create package records for each package in the request
        for package_name in request.package_names:
            package_record = InstallationPackage(
                installation_request_id=request_id,
                package_name=package_name,
                package_manager="auto",  # Let the agent determine the best package manager
            )
            db.add(package_record)

        # Commit the installation records first
        db.commit()

        # Create a single message for the entire package installation request
        command_message = create_command_message(
            command_type="generic_command",
            parameters={
                "command_type": "install_packages",
                "parameters": {
                    "request_id": request_id,
                    "packages": [
                        {"package_name": pkg_name, "package_manager": "auto"}
                        for pkg_name in request.package_names
                    ],
                    "requested_by": request.requested_by,
                    "requested_at": now.isoformat(),
                },
            },
        )

        # Queue the single message using the server queue manager
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Update request status to in_progress
        installation_request.status = "in_progress"
        installation_request.updated_at = now

        # Final commit for status updates
        db.commit()

        # Audit log the package installation request on the MAIN engine — the
        # audit trail is server-global, not tenant-scoped.
        with main_session_local() as audit_session:
            AuditService.log(
                db=audit_session,
                action_type=ActionType.UPDATE,
                entity_type=EntityType.PACKAGE,
                description=_("Queued installation of %d packages on host %s")
                % (len(request.package_names), host.fqdn),
                result=Result.SUCCESS,
                user_id=audit_user_id,
                username=current_user,
                entity_id=host_id,
                entity_name=host.fqdn,
                details={
                    "request_id": request_id,
                    "packages": request.package_names,
                    "requested_by": request.requested_by,
                },
            )

        return PackageInstallResponse(
            success=True,
            message=_("Successfully queued %d packages for installation")
            % len(request.package_names),
            request_id=request_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to queue package installation: %s") % str(e),
        ) from e


async def uninstall_packages_operation(  # NOSONAR
    host_id: str,
    request: PackageUninstallRequest,
    db: Session,
    current_user: str,
) -> PackageUninstallResponse:
    """
    Queue package uninstallation for a specific host using UUID-based grouping.

    Creates a single uninstallation request with multiple packages grouped under one UUID.
    The agent will receive this UUID and return it when reporting completion.

    Phase 13.1: this is a helper (not a FastAPI endpoint) invoked by the
    ``uninstall_packages`` route in ``packages.py``.  The caller passes the
    TENANT-scoped ``db`` session (used for the request DATA) plus the
    ``current_user`` userid string.  User identities / roles are server-global
    and live on the MAIN engine, so authorization is resolved on an explicit
    main-engine session below — never on the tenant ``db``.  The audit trail is
    also server-global and is written on a separate main-engine session.
    """
    try:
        # Resolve authorization on the MAIN engine — user/role data is
        # server-global and is NOT present in the tenant ``db``.
        main_session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with main_session_local() as session:
            user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.REMOVE_PACKAGE):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: REMOVE_PACKAGE role required"),
                )

            # Capture the user id while the session is still open; the audit
            # log (written on a fresh main-engine session) needs it later.
            audit_user_id = user.id

        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Validate that packages are not empty
        if not request.package_names:
            raise HTTPException(
                status_code=400,
                detail=_("No packages specified for uninstallation"),
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Generate a single UUID for this entire uninstallation request
        request_id = str(uuid.uuid4())

        # Create the primary uninstallation request record
        installation_request = InstallationRequest(
            id=request_id,
            host_id=host_id,
            requested_by=request.requested_by,
            requested_at=now,
            status="pending",
            operation_type="uninstall",
            created_at=now,
            updated_at=now,
        )
        db.add(installation_request)

        # Create package records for each package in the request
        for package_name in request.package_names:
            package_record = InstallationPackage(
                installation_request_id=request_id,
                package_name=package_name,
                package_manager="auto",  # Let the agent determine the best package manager
            )
            db.add(package_record)

        # Commit the uninstallation records first
        db.commit()

        # Create a single message for the entire package uninstallation request
        command_message = create_command_message(
            command_type="generic_command",
            parameters={
                "command_type": "uninstall_packages",
                "parameters": {
                    "request_id": request_id,
                    "packages": [
                        {"package_name": pkg_name, "package_manager": "auto"}
                        for pkg_name in request.package_names
                    ],
                    "requested_by": request.requested_by,
                    "requested_at": now.isoformat(),
                },
            },
        )

        # Queue the single message using the server queue manager
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Update request status to in_progress
        installation_request.status = "in_progress"
        installation_request.updated_at = now

        # Final commit for status updates
        db.commit()

        # Audit log the package uninstallation request on the MAIN engine — the
        # audit trail is server-global, not tenant-scoped.
        with main_session_local() as audit_session:
            AuditService.log(
                db=audit_session,
                action_type=ActionType.UPDATE,
                entity_type=EntityType.PACKAGE,
                description=_("Queued uninstallation of %d packages on host %s")
                % (len(request.package_names), host.fqdn),
                result=Result.SUCCESS,
                user_id=audit_user_id,
                username=current_user,
                entity_id=host_id,
                entity_name=host.fqdn,
                details={
                    "request_id": request_id,
                    "packages": request.package_names,
                    "requested_by": request.requested_by,
                },
            )

        return PackageUninstallResponse(
            success=True,
            message=_("Successfully queued %d packages for uninstallation")
            % len(request.package_names),
            request_id=request_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to queue package uninstallation: %s") % str(e),
        ) from e
