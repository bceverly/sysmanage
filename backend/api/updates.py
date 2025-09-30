"""
This module houses the API routes for package update management in SysManage.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from sqlalchemy import and_, desc
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import db, models
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import create_command_message

logger = logging.getLogger(__name__)

router = APIRouter()


class PackageUpdateInfo(BaseModel):
    """Represents package update information from agent."""

    package_name: str
    current_version: Optional[str] = None
    available_version: str
    package_manager: str
    source: Optional[str] = None
    is_security_update: bool = False
    is_system_update: bool = False
    requires_reboot: bool = False
    update_size_bytes: Optional[int] = None
    bundle_id: Optional[str] = None
    repository: Optional[str] = None
    channel: Optional[str] = None


class UpdatesReport(BaseModel):
    """Complete update report from agent."""

    available_updates: List[PackageUpdateInfo]
    total_updates: int
    security_updates: int
    system_updates: int
    application_updates: int
    platform: str
    requires_reboot: bool = False


class UpdateExecutionRequest(BaseModel):
    """Request to execute package updates."""

    host_ids: List[str]
    package_names: List[str]
    package_managers: Optional[List[str]] = None

    @validator("host_ids")
    def validate_host_ids(cls, host_ids):  # pylint: disable=no-self-argument
        if not host_ids:
            raise ValueError("host_ids cannot be empty")
        return host_ids

    @validator("package_names")
    def validate_package_names(cls, package_names):  # pylint: disable=no-self-argument
        if not package_names:
            raise ValueError("package_names cannot be empty")
        return package_names

    @validator("package_managers", pre=True)
    def validate_package_managers(
        cls, package_managers
    ):  # pylint: disable=no-self-argument
        # Convert empty array to None
        if package_managers == []:
            return None
        return package_managers


class UpdateStatsSummary(BaseModel):
    """Summary statistics for updates across hosts."""

    total_hosts: int
    hosts_with_updates: int
    total_updates: int
    security_updates: int
    system_updates: int
    application_updates: int


@router.post("/report/{host_id}")
async def report_updates(
    host_id: str, updates_report: UpdatesReport, dependencies=Depends(JWTBearer())
):
    """Receive and store update information from agents."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Verify host exists
            host = session.query(models.Host).filter(models.Host.id == host_id).first()
            if not host:
                raise HTTPException(status_code=404, detail=_("Host not found"))

            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Clear existing updates for this host
            session.query(models.PackageUpdate).filter(
                models.PackageUpdate.host_id == host_id
            ).delete()

            # Store new updates
            for update_info in updates_report.available_updates:
                # Map old agent fields to new schema
                update_type = "package"  # default
                if update_info.is_security_update:
                    update_type = "security"
                elif update_info.is_system_update:
                    update_type = "system"

                package_update = models.PackageUpdate(
                    host_id=host_id,
                    package_name=update_info.package_name,
                    current_version=update_info.current_version or "unknown",
                    available_version=update_info.available_version,
                    package_manager=update_info.package_manager,
                    update_type=update_type,
                    priority=None,  # Not provided by agent
                    description=None,  # Not provided by agent
                    size_bytes=update_info.update_size_bytes,
                    requires_reboot=update_info.requires_reboot,
                    discovered_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(package_update)

            session.commit()
            return {
                "status": "success",
                "updates_stored": len(updates_report.available_updates),
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to store updates: %s") % str(e)
        ) from e


@router.get("/summary")
async def get_update_summary(dependencies=Depends(JWTBearer())):
    """Get summary statistics for package updates across all hosts, including update results."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Count total hosts
            total_hosts = (
                session.query(models.Host).filter(models.Host.active.is_(True)).count()
            )

            # Count hosts with updates
            hosts_with_updates = (
                session.query(models.PackageUpdate.host_id).distinct().count()
            )

            # Count total updates
            total_updates = session.query(models.PackageUpdate).count()

            # Count security updates (based on update_type)
            security_updates = (
                session.query(models.PackageUpdate)
                .filter(models.PackageUpdate.update_type == "security")
                .count()
            )

            # Count system updates (based on update_type)
            system_updates = (
                session.query(models.PackageUpdate)
                .filter(models.PackageUpdate.update_type == "system")
                .count()
            )

            # Count application updates (based on update_type)
            application_updates = (
                session.query(models.PackageUpdate)
                .filter(models.PackageUpdate.update_type == "enhancement")
                .count()
            )

            # Try to get update results from the update handlers module's cache
            update_results = {}
            try:
                import backend.api.update_handlers as update_handlers_module

                if hasattr(update_handlers_module, "handle_update_apply_result"):
                    handler = getattr(
                        update_handlers_module, "handle_update_apply_result"
                    )
                    if hasattr(handler, "update_results_cache"):
                        update_results = handler.update_results_cache.copy()
            except Exception:  # nosec B110
                pass  # If we can't get the cache, just return empty results

            return {
                "total_hosts": total_hosts,
                "hosts_with_updates": hosts_with_updates,
                "total_updates": total_updates,
                "security_updates": security_updates,
                "system_updates": system_updates,
                "application_updates": application_updates,
                "results": update_results,
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get update summary: %s") % str(e)
        ) from e


# OS Version Upgrade specific endpoints

OS_UPGRADE_PACKAGE_MANAGERS = [
    "ubuntu-release",
    "fedora-release",
    "opensuse-release",
    "macos-upgrade",
    "macOS Update",  # Agent sends this for macOS system updates
    "windows-upgrade",
    "openbsd-upgrade",
    "freebsd-upgrade",
]


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

            return {
                "os_upgrades_summary": summary,
                "total_upgrades": len(all_upgrades),
                "total_hosts_with_upgrades": len(
                    set(update.host_id for update in all_upgrades)
                ),
                "os_types_with_upgrades": list(summary_by_os.keys()),
            }

    except Exception as e:
        logger.error("Error fetching OS upgrades summary: %s", e)
        raise HTTPException(status_code=500, detail=_("Internal server error")) from e


@router.post("/execute-os-upgrades")
async def execute_os_upgrades(
    request: UpdateExecutionRequest, dependencies=Depends(JWTBearer())
):
    """
    Execute OS version upgrades on specified hosts.
    This is a specialized version of execute_updates that adds extra safety checks for OS upgrades.
    """
    try:
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


@router.get("/{host_id}")
async def get_host_updates(
    host_id: str,
    *,
    package_manager: Optional[str] = Query(None),
    security_only: Optional[bool] = Query(None),
    system_only: Optional[bool] = Query(None),
    application_only: Optional[bool] = Query(None),
    dependencies=Depends(JWTBearer()),
):
    """Get package updates for a specific host."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Verify host exists
            host = session.query(models.Host).filter(models.Host.id == host_id).first()
            if not host:
                raise HTTPException(status_code=404, detail=_("Host not found"))

            # Build query with filters
            query = session.query(models.PackageUpdate).filter(
                models.PackageUpdate.host_id == host_id
            )

            if package_manager:
                query = query.filter(
                    models.PackageUpdate.package_manager == package_manager
                )

            if security_only:
                query = query.filter(models.PackageUpdate.update_type == "security")

            if system_only:
                query = query.filter(models.PackageUpdate.update_type == "system")

            if application_only:
                query = query.filter(models.PackageUpdate.update_type == "enhancement")

            updates = query.order_by(models.PackageUpdate.package_name).all()

            # Convert to dict format
            update_list = []
            for update in updates:
                update_dict = {
                    "id": str(update.id),
                    "host_id": host_id,  # Add missing host_id
                    "hostname": host.fqdn,  # Add missing hostname
                    "package_name": update.package_name,
                    "current_version": update.current_version,
                    "available_version": update.available_version,
                    "package_manager": update.package_manager,
                    "update_type": update.update_type,
                    # Add frontend-expected boolean fields
                    "is_security_update": update.update_type == "security",
                    "is_system_update": update.update_type == "system",
                    "priority": update.priority,
                    "description": update.description,
                    "requires_reboot": update.requires_reboot,
                    "size_bytes": update.size_bytes,
                    "discovered_at": (
                        update.discovered_at.isoformat()
                        if update.discovered_at
                        else None
                    ),
                    "created_at": (
                        update.created_at.isoformat() if update.created_at else None
                    ),
                    "updated_at": (
                        update.updated_at.isoformat() if update.updated_at else None
                    ),
                }
                update_list.append(update_dict)

            return {
                "host_id": host_id,
                "hostname": host.fqdn,
                "updates": update_list,
                "total_updates": len(update_list),
                "security_updates": len(
                    [u for u in updates if u.update_type == "security"]
                ),
                "system_updates": len(
                    [u for u in updates if u.update_type == "system"]
                ),
                "application_updates": len(
                    [u for u in updates if u.update_type == "enhancement"]
                ),
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get host updates: %s") % str(e)
        ) from e


@router.get("/")
async def get_all_updates(  # pylint: disable=too-many-positional-arguments
    security_only: Optional[bool] = Query(None),
    system_only: Optional[bool] = Query(None),
    application_only: Optional[bool] = Query(None),
    package_manager: Optional[str] = Query(None),
    limit: Optional[int] = Query(100),
    offset: Optional[int] = Query(0),
    dependencies=Depends(JWTBearer()),
):
    """Get package updates across all hosts."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Build base query
            query = session.query(models.PackageUpdate, models.Host.fqdn).join(
                models.Host
            )

            # Apply filters
            if security_only:
                query = query.filter(models.PackageUpdate.update_type == "security")

            if system_only:
                query = query.filter(models.PackageUpdate.update_type == "system")

            if application_only:
                query = query.filter(models.PackageUpdate.update_type == "enhancement")

            if package_manager:
                query = query.filter(
                    models.PackageUpdate.package_manager == package_manager
                )

            # Get total count before pagination
            total_count = query.count()

            # Apply pagination and ordering
            updates_with_hosts = (
                query.order_by(
                    models.PackageUpdate.update_type,
                    models.Host.fqdn,
                    models.PackageUpdate.package_name,
                )
                .limit(limit)
                .offset(offset)
                .all()
            )

            # Format response
            update_list = []
            for update, hostname in updates_with_hosts:
                update_dict = {
                    "id": str(update.id),
                    "host_id": str(update.host_id),
                    "hostname": hostname,
                    "package_name": update.package_name,
                    "current_version": update.current_version,
                    "available_version": update.available_version,
                    "package_manager": update.package_manager,
                    "update_type": update.update_type,
                    # Add frontend-expected boolean fields
                    "is_security_update": update.update_type == "security",
                    "is_system_update": update.update_type == "system",
                    "priority": update.priority,
                    "description": update.description,
                    "requires_reboot": update.requires_reboot,
                    "size_bytes": update.size_bytes,
                    "discovered_at": (
                        update.discovered_at.isoformat()
                        if update.discovered_at
                        else None
                    ),
                    "created_at": (
                        update.created_at.isoformat() if update.created_at else None
                    ),
                    "updated_at": (
                        update.updated_at.isoformat() if update.updated_at else None
                    ),
                }
                update_list.append(update_dict)

            return {
                "updates": update_list,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get updates: %s") % str(e)
        ) from e


@router.post("/execute")
async def execute_updates(
    request: UpdateExecutionRequest, dependencies=Depends(JWTBearer())
):
    """Execute package updates on specified hosts."""
    try:
        logger.info(
            "Received update execution request: host_ids=%s, package_names=%s, package_managers=%s",
            request.host_ids,
            request.package_names,
            request.package_managers,
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
                            "success": False,
                            "error": _("Host not found or inactive"),
                        }
                    )
                    continue

                # Get available updates for the packages
                updates_query = session.query(models.PackageUpdate).filter(
                    and_(
                        models.PackageUpdate.host_id == host_id,
                        models.PackageUpdate.package_name.in_(request.package_names),
                    )
                )

                if request.package_managers:
                    updates_query = updates_query.filter(
                        models.PackageUpdate.package_manager.in_(
                            request.package_managers
                        )
                    )

                updates = updates_query.all()

                if not updates:
                    results.append(
                        {
                            "host_id": host_id,
                            "hostname": host.fqdn,
                            "success": False,
                            "error": _(
                                "No matching updates found for specified packages"
                            ),
                        }
                    )
                    continue

                # Create execution log entries
                execution_logs = []
                for update in updates:
                    # Update status to updating
                    update.status = "updating"
                    update.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

                    # Create execution log
                    execution_log = models.UpdateExecutionLog(
                        host_id=host_id,
                        package_update_id=update.id,
                        package_name=update.package_name,
                        package_manager=update.package_manager,
                        from_version=update.current_version,
                        to_version=update.available_version,
                        status="pending",
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(execution_log)
                    execution_logs.append(execution_log)

                session.commit()

                # Send command to agent via WebSocket
                try:
                    command_message = create_command_message(
                        "apply_updates",
                        {
                            "package_names": request.package_names,
                            "package_managers": request.package_managers,
                        },
                    )

                    await connection_manager.send_to_host(host.id, command_message)

                    results.append(
                        {
                            "host_id": host_id,
                            "hostname": host.fqdn,
                            "success": True,
                            "message": _("Update execution started"),
                            "packages_count": len(updates),
                        }
                    )

                except (ConnectionError, ValueError, RuntimeError) as e:
                    # Rollback execution status on WebSocket failure
                    # Note: status column was removed in new schema
                    # for update in updates:
                    #     update.status = "available"
                    for log in execution_logs:
                        log.status = "failed"
                        log.error_message = _("Failed to send command: %s") % str(e)
                    session.commit()

                    results.append(
                        {
                            "host_id": host_id,
                            "hostname": host.fqdn,
                            "success": False,
                            "error": _("Failed to send update command: %s") % str(e),
                        }
                    )

            return {"results": results}

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        logger.error("Update execution failed: %s", str(e))
        logger.error("Full traceback:\n%s", error_details)
        raise HTTPException(
            status_code=500, detail=_("Failed to execute updates: %s") % str(e)
        ) from e


@router.get("/execution-log/{host_id}")
async def get_execution_log(
    host_id: str,
    limit: Optional[int] = Query(50),
    offset: Optional[int] = Query(0),
    dependencies=Depends(JWTBearer()),
):
    """Get update execution log for a host."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Verify host exists
            host = session.query(models.Host).filter(models.Host.id == host_id).first()
            if not host:
                raise HTTPException(status_code=404, detail=_("Host not found"))

            # Get execution logs
            logs = (
                session.query(models.UpdateExecutionLog)
                .filter(models.UpdateExecutionLog.host_id == host_id)
                .order_by(desc(models.UpdateExecutionLog.created_at))
                .limit(limit)
                .offset(offset)
                .all()
            )

            log_list = []
            for log in logs:
                log_dict = {
                    "id": str(log.id),
                    "package_name": log.package_name,
                    "package_manager": log.package_manager,
                    "from_version": log.from_version,
                    "to_version": log.to_version,
                    "status": log.status,
                    "started_at": log.started_at,
                    "completed_at": log.completed_at,
                    "success": log.success,
                    "error_message": log.error_message,
                    "created_at": log.created_at,
                }
                log_list.append(log_dict)

            return {
                "host_id": host_id,
                "hostname": host.fqdn,
                "execution_logs": log_list,
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get execution log: %s") % str(e)
        ) from e


@router.get("/results", response_model=UpdateStatsSummary)
async def get_update_results(dependencies=Depends(JWTBearer())):
    """Get recent update application results from agents."""
    try:
        logger.info("SUCCESS: get_update_results called successfully")
        return UpdateStatsSummary(
            total_hosts=0,
            hosts_with_updates=0,
            total_updates=0,
            security_updates=0,
            system_updates=0,
            application_updates=0,
        )
    except Exception as e:
        logger.error("Error in get_update_results: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to get update results: %s") % str(e)
        ) from e


@router.get("/update-status")
async def get_update_status(dependencies=Depends(JWTBearer())):
    """Get recent update application results from agents."""
    try:
        # Try to get the update results cache from the global scope
        import backend.api.agent as agent_module

        if hasattr(agent_module, "handle_update_apply_result"):
            handler = getattr(agent_module, "handle_update_apply_result")
            if hasattr(handler, "update_results_cache"):
                results = handler.update_results_cache.copy()
                return {"results": results}

        return {"results": {}}
    except Exception as e:
        logger.error("Error fetching update status: %s", e)
        return {"results": {}, "error": "Failed to fetch update status"}
