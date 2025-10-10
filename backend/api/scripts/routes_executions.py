"""
API routes for script execution and execution log management.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    server_queue_manager,
)

from .models import (
    ScriptExecutionLogResponse,
    ScriptExecutionRequest,
    ScriptExecutionResponse,
    ScriptExecutionsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/execute", response_model=ScriptExecutionResponse)
async def execute_script(
    execution_request: ScriptExecutionRequest,
    current_user=Depends(get_current_user),
):
    """Execute a script on a remote host."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            # Check if user has permission to run scripts
            auth_user = (
                db_session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not auth_user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if auth_user._role_cache is None:
                auth_user.load_role_cache(db_session)

            if not auth_user.has_role(SecurityRoles.RUN_SCRIPT):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: RUN_SCRIPT role required"),
                )

            # Verify host exists and is active
            host = (
                db_session.query(models.Host)
                .filter(models.Host.id == execution_request.host_id)
                .first()
            )

            if not host:
                raise HTTPException(status_code=404, detail=_("Host not found"))

            if not host.active:
                raise HTTPException(status_code=400, detail=_("Host is not active"))

            # Prepare script execution data
            execution_id = str(uuid.uuid4())
            execution_uuid = str(uuid.uuid4())  # Separate UUID for agent tracking
            script_content = execution_request.script_content
            shell_type = execution_request.shell_type
            script_name = execution_request.script_name

            # If using saved script, fetch its details
            if execution_request.saved_script_id:
                saved_script = (
                    db_session.query(models.SavedScript)
                    .filter(models.SavedScript.id == execution_request.saved_script_id)
                    .first()
                )

                if not saved_script:
                    raise HTTPException(
                        status_code=404, detail=_("Saved script not found")
                    )

                if not saved_script.is_active:
                    raise HTTPException(
                        status_code=400, detail=_("Script is not active")
                    )

                script_content = saved_script.content
                shell_type = saved_script.shell_type
                script_name = saved_script.name

                # Use saved script's run_as_user if not overridden
                if not execution_request.run_as_user:
                    execution_request.run_as_user = saved_script.run_as_user

            # Create execution log entry
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            execution_log = models.ScriptExecutionLog(
                host_id=execution_request.host_id,
                saved_script_id=execution_request.saved_script_id,
                script_name=script_name,
                script_content=script_content,
                shell_type=shell_type,
                run_as_user=execution_request.run_as_user,
                requested_by=current_user,
                execution_id=execution_id,
                execution_uuid=execution_uuid,
                status="pending",
                created_at=now,
                updated_at=now,
            )

            db_session.add(execution_log)
            # Don't commit yet - queue the message in the same transaction

            # Queue script execution command for outbound delivery to agent
            command_data = {
                "execution_id": execution_id,
                "execution_uuid": execution_uuid,  # Send the tracking UUID to agent
                "script_content": script_content,
                "shell_type": shell_type,
                "run_as_user": execution_request.run_as_user,
                "script_name": script_name or "ad-hoc script",
            }

            # Queue the message for delivery to the agent
            logger.info(
                "Queueing script execution to host %d (%s)",
                host.id,
                host.fqdn,
            )

            try:
                queue_message_id = server_queue_manager.enqueue_message(
                    message_type="command",
                    message_data=command_data,
                    direction=QueueDirection.OUTBOUND,
                    host_id=host.id,
                    priority=Priority.HIGH,
                    correlation_id=execution_id,
                    db=db_session,
                )

                # Now commit both the execution log AND the queued message together
                db_session.commit()

                logger.info(
                    "Script execution %s queued with message ID %s for host %d (%s)",
                    execution_id,
                    queue_message_id,
                    host.id,
                    host.fqdn,
                )
            except Exception as e:
                # Update execution log to failed
                execution_log.status = "failed"
                execution_log.error_message = _(
                    "Failed to queue script execution: {}"
                ).format(str(e))
                execution_log.updated_at = datetime.now(timezone.utc).replace(
                    tzinfo=None
                )
                db_session.commit()

                logger.error("Failed to queue script execution: %s", e)
                raise HTTPException(
                    status_code=500,
                    detail=_("Failed to queue script execution"),
                ) from e

            logger.info(
                "Script execution %s requested by %s for host %d",
                execution_id,
                current_user,
                execution_request.host_id,
            )

            return ScriptExecutionResponse(
                execution_id=execution_id,
                status="pending",
                message=_("Script execution queued for delivery"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error executing script: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to execute script")
        ) from e


@router.get("/executions/", response_model=ScriptExecutionsResponse)
async def get_script_executions(
    current_user=Depends(get_current_user),
    host_id: Optional[str] = Query(None, description="Filter by host ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, description="Page number (1-based)"),
    limit: int = Query(50, description="Maximum number of results per page"),
):
    """Get script execution logs with pagination."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            # Build base query
            base_query = db_session.query(models.ScriptExecutionLog).join(
                models.Host, models.ScriptExecutionLog.host_id == models.Host.id
            )

            if host_id:
                base_query = base_query.filter(
                    models.ScriptExecutionLog.host_id == host_id
                )

            if status:
                base_query = base_query.filter(
                    models.ScriptExecutionLog.status == status
                )

            # Get total count
            total = base_query.count()

            # Calculate offset and pages
            offset = (page - 1) * limit
            pages = (total + limit - 1) // limit if total > 0 else 1

            # Get paginated results
            query = base_query.order_by(desc(models.ScriptExecutionLog.created_at))
            query = query.offset(offset).limit(limit)

            executions = query.all()

            # Add host FQDN to response and ensure UUID conversion
            execution_results = []
            for execution in executions:
                execution_results.append(
                    ScriptExecutionLogResponse(
                        id=str(execution.id),
                        host_id=str(execution.host_id),
                        host_fqdn=execution.host.fqdn,
                        saved_script_id=(
                            str(execution.saved_script_id)
                            if execution.saved_script_id
                            else None
                        ),
                        script_name=execution.script_name,
                        shell_type=execution.shell_type,
                        run_as_user=execution.run_as_user,
                        requested_by=execution.requested_by,
                        execution_id=execution.execution_id,
                        status=execution.status,
                        started_at=execution.started_at,
                        completed_at=execution.completed_at,
                        exit_code=execution.exit_code,
                        stdout_output=execution.stdout_output,
                        stderr_output=execution.stderr_output,
                        error_message=execution.error_message,
                        created_at=execution.created_at,
                        updated_at=execution.updated_at,
                    )
                )

            return ScriptExecutionsResponse(
                executions=execution_results, total=total, page=page, pages=pages
            )

    except Exception as e:
        logger.error("Error fetching script executions: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to fetch script executions")
        ) from e


@router.delete("/executions/{execution_id}")
async def delete_script_execution(
    execution_id: str,
    current_user=Depends(get_current_user),
):
    """Delete a specific script execution by execution ID."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            # Check if user has permission to delete script executions
            auth_user = (
                db_session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not auth_user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if auth_user._role_cache is None:
                auth_user.load_role_cache(db_session)

            if not auth_user.has_role(SecurityRoles.DELETE_SCRIPT_EXECUTION):
                raise HTTPException(
                    status_code=403,
                    detail=_(
                        "Permission denied: DELETE_SCRIPT_EXECUTION role required"
                    ),
                )

            execution = (
                db_session.query(models.ScriptExecutionLog)
                .filter(models.ScriptExecutionLog.execution_id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(
                    status_code=404, detail=_("Script execution not found")
                )

            db_session.delete(execution)
            db_session.commit()

            logger.info(
                "Deleted script execution %s by user %s", execution_id, current_user
            )
            return {"message": _("Script execution deleted successfully")}
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error("Error deleting script execution %s: %s", execution_id, e)
        raise HTTPException(
            status_code=500, detail=_("Failed to delete script execution")
        ) from e


@router.delete("/executions/bulk")
async def delete_script_executions_bulk(
    execution_ids: List[str] = Body(...),
    current_user=Depends(get_current_user),
):
    """Delete multiple script executions by execution IDs."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            # Check if user has permission to delete script executions
            auth_user = (
                db_session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not auth_user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if auth_user._role_cache is None:
                auth_user.load_role_cache(db_session)

            if not auth_user.has_role(SecurityRoles.DELETE_SCRIPT_EXECUTION):
                raise HTTPException(
                    status_code=403,
                    detail=_(
                        "Permission denied: DELETE_SCRIPT_EXECUTION role required"
                    ),
                )

            deleted_count = (
                db_session.query(models.ScriptExecutionLog)
                .filter(models.ScriptExecutionLog.execution_id.in_(execution_ids))
                .delete(synchronize_session=False)
            )

            db_session.commit()

            logger.info(
                "Bulk deleted %d script executions by user %s",
                deleted_count,
                current_user,
            )
            return {
                "message": _("Script executions deleted successfully"),
                "deleted_count": deleted_count,
            }
    except Exception as e:
        db_session.rollback()
        logger.error("Error bulk deleting script executions: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to delete script executions")
        ) from e


@router.get("/executions/{execution_id}", response_model=ScriptExecutionLogResponse)
async def get_script_execution(
    execution_id: str,
    current_user=Depends(get_current_user),
):
    """Get a specific script execution by execution ID."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            execution = (
                db_session.query(models.ScriptExecutionLog)
                .join(models.Host, models.ScriptExecutionLog.host_id == models.Host.id)
                .filter(models.ScriptExecutionLog.execution_id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(
                    status_code=404, detail=_("Script execution not found")
                )

            return ScriptExecutionLogResponse(
                id=str(execution.id),
                host_id=str(execution.host_id),
                host_fqdn=execution.host.fqdn,
                saved_script_id=(
                    str(execution.saved_script_id)
                    if execution.saved_script_id
                    else None
                ),
                script_name=execution.script_name,
                shell_type=execution.shell_type,
                run_as_user=execution.run_as_user,
                requested_by=execution.requested_by,
                execution_id=execution.execution_id,
                status=execution.status,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                exit_code=execution.exit_code,
                stdout_output=execution.stdout_output,
                stderr_output=execution.stderr_output,
                error_message=execution.error_message,
                created_at=execution.created_at,
                updated_at=execution.updated_at,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching script execution %s: %s", execution_id, e)
        raise HTTPException(
            status_code=500, detail=_("Failed to fetch script execution")
        ) from e
