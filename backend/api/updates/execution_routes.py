"""API routes for executing package updates."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

from .models import UpdateExecutionRequest

logger = logging.getLogger(__name__)
router = APIRouter()
queue_ops = QueueOperations()


@router.post("/execute")
async def execute_updates(
    request: UpdateExecutionRequest,
    dependencies=Depends(JWTBearer()),
    current_user: str = Depends(get_current_user),
):
    """Execute package updates on specified hosts."""
    try:
        # Check if user has permission to apply software updates
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

            if not user.has_role(SecurityRoles.APPLY_SOFTWARE_UPDATE):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: APPLY_SOFTWARE_UPDATE role required"),
                )

        logger.info(
            "Received update execution request: host_ids=%s, package_names=%s, package_managers=%s",
            request.host_ids,
            request.package_names,
            request.package_managers,
        )
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

                    queue_ops.enqueue_message(
                        message_type="command",
                        message_data=command_message,
                        direction=QueueDirection.OUTBOUND,
                        host_id=host.id,
                        db=session,
                    )
                    # Commit the session to persist the queued message
                    session.commit()

                    # Audit log the update execution - one message per package per host
                    for update in updates:
                        AuditService.log(
                            db=session,
                            action_type=ActionType.UPDATE,
                            entity_type=EntityType.PACKAGE,
                            description=f"Initiated update of package {update.package_name} from {update.current_version} to {update.available_version} on host {host.fqdn}",
                            result=Result.SUCCESS,
                            user_id=user.id,
                            username=current_user,
                            entity_id=host_id,
                            entity_name=f"{host.fqdn}/{update.package_name}",
                            details={
                                "host_id": host_id,
                                "host_fqdn": host.fqdn,
                                "package_name": update.package_name,
                                "package_manager": update.package_manager,
                                "from_version": update.current_version,
                                "to_version": update.available_version,
                            },
                        )

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
