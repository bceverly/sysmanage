"""API routes for OS version upgrade management."""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import sessionmaker
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import create_command_message
from .constants import OS_UPGRADE_PACKAGE_MANAGERS
from .models import UpdateExecutionRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/os-upgrades")
async def get_os_upgrades(
    host_id: Optional[str] = Query(None), dependencies=Depends(JWTBearer())
):
    """Get available OS version upgrades for all hosts or a specific host."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Build query for OS upgrades
            query = session.query(models.PackageUpdate).filter(
                models.PackageUpdate.package_manager.in_(OS_UPGRADE_PACKAGE_MANAGERS)
            )

            if host_id:
                # Verify host exists first
                host = (
                    session.query(models.Host).filter(models.Host.id == host_id).first()
                )
                if not host:
                    raise HTTPException(status_code=404, detail=_("Host not found"))
                query = query.filter(models.PackageUpdate.host_id == host_id)

            # Order by host and package manager
            updates = query.order_by(
                models.PackageUpdate.host_id,
                models.PackageUpdate.package_manager,
                models.PackageUpdate.package_name,
            ).all()

            # Format the response with host information
            results = []
            for update in updates:
                host = update.host
                results.append(
                    {
                        "id": str(update.id),
                        "host_id": str(update.host_id),
                        "host_fqdn": host.fqdn,
                        "host_platform": host.platform,
                        "package_name": update.package_name,
                        "current_version": update.current_version,
                        "available_version": update.available_version,
                        "package_manager": update.package_manager,
                        "update_type": update.update_type,
                        "requires_reboot": update.requires_reboot,
                        "size_bytes": update.size_bytes,
                        "discovered_at": (
                            update.discovered_at.isoformat()
                            if update.discovered_at
                            else None
                        ),
                    }
                )

            return {
                "os_upgrades": results,
                "total_count": len(results),
                "hosts_with_upgrades": len(set(update.host_id for update in updates)),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching OS upgrades: %s", e)
        raise HTTPException(status_code=500, detail=_("Internal server error")) from e


@router.get("/os-upgrades/summary")
async def get_os_upgrades_summary(dependencies=Depends(JWTBearer())):
    """Get summary of OS upgrades across all hosts."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Get OS upgrades by package manager (OS type)
            query = session.query(models.PackageUpdate).filter(
                models.PackageUpdate.package_manager.in_(OS_UPGRADE_PACKAGE_MANAGERS)
            )

            all_upgrades = query.all()

            # Group by package manager (OS type)
            summary_by_os = {}
            for update in all_upgrades:
                os_type = update.package_manager
                if os_type not in summary_by_os:
                    summary_by_os[os_type] = {
                        "package_manager": os_type,
                        "total_hosts": 0,
                        "host_ids": set(),
                        "upgrades": [],
                    }

                summary_by_os[os_type]["host_ids"].add(update.host_id)
                summary_by_os[os_type]["upgrades"].append(
                    {
                        "host_id": update.host_id,
                        "host_fqdn": update.host.fqdn,
                        "package_name": update.package_name,
                        "current_version": update.current_version,
                        "available_version": update.available_version,
                        "update_type": update.update_type,
                    }
                )

            # Convert to final format
            summary = []
            for os_type, data in summary_by_os.items():
                data["total_hosts"] = len(data["host_ids"])
                del data["host_ids"]  # Remove set, not JSON serializable
                summary.append(data)

            # Count total hosts
            total_hosts = (
                session.query(models.Host).filter(models.Host.active.is_(True)).count()
            )

            return {
                "os_upgrades_summary": summary,
                "total_os_upgrades": len(all_upgrades),
                "hosts_with_os_upgrades": len(
                    set(update.host_id for update in all_upgrades)
                ),
                "total_hosts": total_hosts,
                "os_upgrades_by_type": {
                    os_type: len(data["upgrades"])
                    for os_type, data in summary_by_os.items()
                },
            }

    except Exception as e:
        logger.error("Error fetching OS upgrades summary: %s", e)
        raise HTTPException(status_code=500, detail=_("Internal server error")) from e


@router.post("/execute-os-upgrades")
async def execute_os_upgrades(
    request: UpdateExecutionRequest,
    dependencies=Depends(JWTBearer()),
    current_user: str = Depends(get_current_user),
):
    """
    Execute OS version upgrades on specified hosts.
    This is a specialized version of execute_updates that adds extra safety checks for OS upgrades.
    """
    try:
        # Check if user has permission to apply host OS upgrades
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.APPLY_HOST_OS_UPGRADE):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: APPLY_HOST_OS_UPGRADE role required"),
                )

        logger.info(
            "Received OS upgrade execution request: host_ids=%s, package_managers=%s",
            request.host_ids,
            request.package_managers,
        )

        # Validate that only OS upgrade package managers are specified
        if request.package_managers:
            invalid_managers = set(request.package_managers) - set(
                OS_UPGRADE_PACKAGE_MANAGERS
            )
            if invalid_managers:
                raise HTTPException(
                    status_code=400,
                    detail=_("Invalid package managers for OS upgrades: {}").format(
                        ", ".join(invalid_managers)
                    ),
                )

        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            results = []

            for host_id in request.host_ids:
                # Verify host exists and is active
                host = (
                    session.query(models.Host)
                    .filter(
                        and_(models.Host.id == host_id, models.Host.active.is_(True))
                    )
                    .first()
                )

                if not host:
                    results.append(
                        {
                            "host_id": host_id,
                            "status": "error",
                            "message": _("Host not found or inactive"),
                        }
                    )
                    continue

                # Check if host has OS upgrades available
                os_upgrades_query = session.query(models.PackageUpdate).filter(
                    and_(
                        models.PackageUpdate.host_id == host_id,
                        models.PackageUpdate.package_manager.in_(
                            OS_UPGRADE_PACKAGE_MANAGERS
                        ),
                    )
                )

                if request.package_managers:
                    os_upgrades_query = os_upgrades_query.filter(
                        models.PackageUpdate.package_manager.in_(
                            request.package_managers
                        )
                    )

                if request.package_names:
                    os_upgrades_query = os_upgrades_query.filter(
                        models.PackageUpdate.package_name.in_(request.package_names)
                    )

                available_upgrades = os_upgrades_query.all()

                if not available_upgrades:
                    results.append(
                        {
                            "host_id": host_id,
                            "status": "no_updates",
                            "message": _("No OS upgrades available for this host"),
                        }
                    )
                    continue

                # Check if we can reach the host
                if not connection_manager.get_agent_connection(host.fqdn):
                    results.append(
                        {
                            "host_id": host_id,
                            "status": "error",
                            "message": _("Host is not connected"),
                        }
                    )
                    continue

                # Create the update command message
                packages_to_update = [
                    {
                        "package_name": update.package_name,
                        "current_version": update.current_version,
                        "available_version": update.available_version,
                        "package_manager": update.package_manager,
                    }
                    for update in available_upgrades
                ]

                command_message = create_command_message(
                    "apply_updates", {"packages": packages_to_update}
                )

                # Send command to agent
                success = await connection_manager.send_message_to_agent(
                    host.fqdn, command_message
                )

                if success:
                    # Mark updates as in progress (status column removed)
                    for update in available_upgrades:
                        # update.status = "updating"  # status column removed
                        update.updated_at = datetime.now(timezone.utc).replace(
                            tzinfo=None
                        )

                    session.commit()

                    logger.info(
                        "OS upgrade command sent successfully to host %s (%s): %d upgrades",
                        host_id,
                        host.fqdn,
                        len(available_upgrades),
                    )

                    # Audit log the OS upgrade execution
                    AuditService.log(
                        db=session,
                        action_type=ActionType.UPDATE,
                        entity_type=EntityType.HOST,
                        description=_(
                            "Initiated OS upgrade on host %s with %d upgrade(s)"
                        )
                        % (host.fqdn, len(available_upgrades)),
                        result=Result.SUCCESS,
                        user_id=user.id,
                        username=current_user,
                        entity_id=host_id,
                        entity_name=host.fqdn,
                        details={
                            "upgrades_count": len(available_upgrades),
                            "package_managers": (
                                request.package_managers
                                if request.package_managers
                                else [u.package_manager for u in available_upgrades]
                            ),
                            "package_names": (
                                request.package_names
                                if request.package_names
                                else [u.package_name for u in available_upgrades]
                            ),
                            "requires_reboot": True,
                        },
                    )

                    results.append(
                        {
                            "host_id": host_id,
                            "status": "success",
                            "message": _("OS upgrade command sent successfully"),
                            "upgrades_count": len(available_upgrades),
                            "requires_reboot": True,  # OS upgrades always require reboot
                        }
                    )
                else:
                    results.append(
                        {
                            "host_id": host_id,
                            "status": "error",
                            "message": _("Failed to send OS upgrade command to host"),
                        }
                    )

            return {"results": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error executing OS upgrades: %s", e)
        raise HTTPException(status_code=500, detail=_("Internal server error")) from e
