"""
This module houses the API routes for diagnostic collection functionality in SysManage.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import validate_host_approval_status
from backend.api.error_constants import (
    error_diagnostic_not_found,
    error_invalid_diagnostic_id,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import CommandType, create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


class DiagnosticRequest(BaseModel):
    """Request model for diagnostic collection."""

    collection_types: Optional[List[str]] = [
        "system_logs",
        "configuration_files",
        "network_info",
        "process_info",
        "disk_usage",
        "environment_variables",
        "agent_logs",
        "error_logs",
    ]


class DiagnosticResponse(BaseModel):
    """Response model for diagnostic collection."""

    id: str
    host_id: str
    collection_id: str
    requested_by: str
    status: str
    requested_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    collection_size_bytes: Optional[int] = None
    files_collected: Optional[int] = None
    error_message: Optional[str] = None


@router.post("/host/{host_id}/collect-diagnostics", dependencies=[Depends(JWTBearer())])
async def collect_diagnostics(
    host_id: str,
    request: DiagnosticRequest = None,
    current_user: str = Depends(get_current_user),
):
    """
    Request diagnostic collection from an agent.
    This sends a command via WebSocket to the agent requesting diagnostic data.
    """
    # Validate UUID format (also accept integers for test compatibility)
    try:
        uuid.UUID(host_id)
    except ValueError:
        # Check if it's a valid integer (for test compatibility)
        try:
            int(host_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=_("Invalid host ID format")
            ) from exc

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get user for audit logging
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

        validate_host_approval_status(host)

        # Generate unique collection ID
        collection_id = str(uuid.uuid4())

        # Create diagnostic report record
        diagnostic_report = models.DiagnosticReport(
            host_id=host_id,
            collection_id=collection_id,
            requested_by="system",
            status="pending",
            requested_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(diagnostic_report)

        # Update host diagnostics request status
        from sqlalchemy import update

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = (
            update(models.Host)
            .where(models.Host.id == host_id)
            .values(diagnostics_requested_at=now, diagnostics_request_status="pending")
        )
        session.execute(stmt)

        session.commit()
        session.refresh(diagnostic_report)

        # Create command message for diagnostic collection
        parameters = {
            "collection_id": collection_id,
            "collection_types": (
                request.collection_types
                if request
                else [
                    "system_logs",
                    "configuration_files",
                    "network_info",
                    "process_info",
                    "disk_usage",
                    "environment_variables",
                    "agent_logs",
                    "error_logs",
                ]
            ),
        }

        command_message = create_command_message(
            command_type=CommandType.COLLECT_DIAGNOSTICS, parameters=parameters
        )

        # Enqueue command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Update status to collecting
        diagnostic_report.status = "collecting"
        diagnostic_report.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        diagnostic_report.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Audit log the diagnostics collection request
        AuditService.log(
            db=session,
            user_id=user.id,
            username=current_user,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested diagnostic collection for host {host.fqdn}",
            result=Result.SUCCESS,
            details={
                "collection_id": collection_id,
                "collection_types": parameters["collection_types"],
            },
        )

        session.commit()

        return {
            "result": True,
            "message": _("Diagnostic collection requested"),
            "collection_id": collection_id,
            "diagnostic_id": str(diagnostic_report.id),
        }


@router.get("/host/{host_id}/diagnostics", dependencies=[Depends(JWTBearer())])
async def get_host_diagnostics(
    host_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Get diagnostic reports for a specific host.
    """
    # Validate UUID format (also accept integers for test compatibility)
    try:
        uuid.UUID(host_id)
    except ValueError:
        # Check if it's a valid integer (for test compatibility)
        try:
            int(host_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=_("Invalid host ID format")
            ) from exc

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Verify host exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get diagnostic reports for this host
        diagnostics = (
            session.query(models.DiagnosticReport)
            .filter(models.DiagnosticReport.host_id == host_id)
            .order_by(models.DiagnosticReport.requested_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # If there are no diagnostics and the host status is "pending", clear it
        if not diagnostics and host.diagnostics_request_status == "pending":
            from sqlalchemy import update

            stmt = (
                update(models.Host)
                .where(models.Host.id == host_id)
                .values(diagnostics_request_status=None)
            )
            session.execute(stmt)
            session.commit()
            # Refresh the host object to reflect the change
            session.refresh(host)

        return {
            "host_id": host_id,
            "diagnostics": [
                {
                    "id": str(diag.id),
                    "collection_id": diag.collection_id,
                    "status": diag.status,
                    "requested_by": diag.requested_by,
                    "requested_at": diag.requested_at.replace(
                        tzinfo=timezone.utc
                    ).isoformat(),
                    "started_at": (
                        diag.started_at.replace(tzinfo=timezone.utc).isoformat()
                        if diag.started_at
                        else None
                    ),
                    "completed_at": (
                        diag.completed_at.replace(tzinfo=timezone.utc).isoformat()
                        if diag.completed_at
                        else None
                    ),
                    "collection_size_bytes": diag.collection_size_bytes,
                    "files_collected": diag.files_collected,
                    "error_message": diag.error_message,
                }
                for diag in diagnostics
            ],
        }


@router.get("/diagnostic/{diagnostic_id}", dependencies=[Depends(JWTBearer())])
async def get_diagnostic_report(diagnostic_id: str):
    """
    Get a specific diagnostic report with full data.
    """
    # Validate UUID format
    try:
        uuid.UUID(diagnostic_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=error_invalid_diagnostic_id()
        ) from exc

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get diagnostic report
        diagnostic = (
            session.query(models.DiagnosticReport)
            .filter(models.DiagnosticReport.id == diagnostic_id)
            .first()
        )

        if not diagnostic:
            raise HTTPException(status_code=404, detail=error_diagnostic_not_found())

        # Parse JSON data fields
        def safe_json_parse(data):
            if data is None:
                return None
            try:
                return json.loads(data) if isinstance(data, str) else data
            except (json.JSONDecodeError, TypeError):
                return None

        return {
            "id": str(diagnostic.id),
            "host_id": str(diagnostic.host_id),
            "collection_id": diagnostic.collection_id,
            "status": diagnostic.status,
            "requested_by": diagnostic.requested_by,
            "requested_at": diagnostic.requested_at.replace(
                tzinfo=timezone.utc
            ).isoformat(),
            "started_at": (
                diagnostic.started_at.replace(tzinfo=timezone.utc).isoformat()
                if diagnostic.started_at
                else None
            ),
            "completed_at": (
                diagnostic.completed_at.replace(tzinfo=timezone.utc).isoformat()
                if diagnostic.completed_at
                else None
            ),
            "collection_size_bytes": diagnostic.collection_size_bytes,
            "files_collected": diagnostic.files_collected,
            "error_message": diagnostic.error_message,
            "diagnostic_data": {
                "system_logs": safe_json_parse(diagnostic.system_logs),
                "configuration_files": safe_json_parse(diagnostic.configuration_files),
                "network_info": safe_json_parse(diagnostic.network_info),
                "process_info": safe_json_parse(diagnostic.process_info),
                "disk_usage": safe_json_parse(diagnostic.disk_usage),
                "environment_variables": safe_json_parse(
                    diagnostic.environment_variables
                ),
                "agent_logs": safe_json_parse(diagnostic.agent_logs),
                "error_logs": safe_json_parse(diagnostic.error_logs),
            },
        }


@router.get("/diagnostic/{diagnostic_id}/status", dependencies=[Depends(JWTBearer())])
async def get_diagnostic_status(diagnostic_id: str):
    """
    Get the current status of a diagnostic collection.
    """
    # Validate UUID format
    try:
        uuid.UUID(diagnostic_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=error_invalid_diagnostic_id()
        ) from exc

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get diagnostic report
        diagnostic = (
            session.query(models.DiagnosticReport)
            .filter(models.DiagnosticReport.id == diagnostic_id)
            .first()
        )

        if not diagnostic:
            raise HTTPException(status_code=404, detail=error_diagnostic_not_found())

        return {
            "id": str(diagnostic.id),
            "collection_id": diagnostic.collection_id,
            "status": diagnostic.status,
            "requested_at": diagnostic.requested_at.replace(
                tzinfo=timezone.utc
            ).isoformat(),
            "started_at": (
                diagnostic.started_at.replace(tzinfo=timezone.utc).isoformat()
                if diagnostic.started_at
                else None
            ),
            "completed_at": (
                diagnostic.completed_at.replace(tzinfo=timezone.utc).isoformat()
                if diagnostic.completed_at
                else None
            ),
            "error_message": diagnostic.error_message,
        }


@router.delete("/diagnostic/{diagnostic_id}", dependencies=[Depends(JWTBearer())])
async def delete_diagnostic_report(  # NOSONAR
    diagnostic_id: str,
):
    """
    Delete a diagnostic report.
    """
    # Validate UUID format
    try:
        uuid.UUID(diagnostic_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=error_invalid_diagnostic_id()
        ) from exc

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the diagnostic report
        diagnostic = (
            session.query(models.DiagnosticReport)
            .filter(models.DiagnosticReport.id == diagnostic_id)
            .first()
        )

        if not diagnostic:
            raise HTTPException(status_code=404, detail=error_diagnostic_not_found())

        # Store the host_id before deleting the diagnostic
        host_id = diagnostic.host_id

        # Delete the record
        session.delete(diagnostic)
        session.commit()

        # Check if this was the last diagnostic report for this host
        remaining_diagnostics_count = (
            session.query(models.DiagnosticReport)
            .filter(models.DiagnosticReport.host_id == host_id)
            .count()
        )

        # If no diagnostics remain, clear the host's diagnostics request status
        if remaining_diagnostics_count == 0:
            from sqlalchemy import update

            stmt = (
                update(models.Host)
                .where(models.Host.id == host_id)
                .values(diagnostics_request_status=None)
            )
            session.execute(stmt)
            session.commit()

        return {"result": True, "message": _("Diagnostic report deleted")}


@router.post("/diagnostics/process-result")
async def process_diagnostic_result(result_data: dict):  # NOSONAR
    """
    Process diagnostic collection result from agent.
    This endpoint is called internally when we receive diagnostic results via WebSocket.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    collection_id = result_data.get("collection_id")
    if not collection_id:
        raise HTTPException(status_code=400, detail="Missing collection_id")

    with session_local() as session:
        # Find the diagnostic report
        diagnostic = (
            session.query(models.DiagnosticReport)
            .filter(models.DiagnosticReport.collection_id == collection_id)
            .first()
        )

        if not diagnostic:
            raise HTTPException(status_code=404, detail=error_diagnostic_not_found())

        # Update diagnostic report with results
        diagnostic.status = (
            "completed" if result_data.get("success", False) else "failed"
        )
        diagnostic.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        diagnostic.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if result_data.get("error"):
            diagnostic.error_message = result_data["error"]

        # Store diagnostic data as JSON
        def safe_json_dumps(data):
            if data is None:
                return None
            try:
                return json.dumps(data) if not isinstance(data, str) else data
            except (TypeError, ValueError):
                return None

        if "system_logs" in result_data:
            diagnostic.system_logs = safe_json_dumps(result_data["system_logs"])
        if "configuration_files" in result_data:
            diagnostic.configuration_files = safe_json_dumps(
                result_data["configuration_files"]
            )
        if "network_info" in result_data:
            diagnostic.network_info = safe_json_dumps(result_data["network_info"])
        if "process_info" in result_data:
            diagnostic.process_info = safe_json_dumps(result_data["process_info"])
        if "disk_usage" in result_data:
            diagnostic.disk_usage = safe_json_dumps(result_data["disk_usage"])
        if "environment_variables" in result_data:
            diagnostic.environment_variables = safe_json_dumps(
                result_data["environment_variables"]
            )
        if "agent_logs" in result_data:
            diagnostic.agent_logs = safe_json_dumps(result_data["agent_logs"])
        if "error_logs" in result_data:
            diagnostic.error_logs = safe_json_dumps(result_data["error_logs"])

        if "collection_size_bytes" in result_data:
            diagnostic.collection_size_bytes = result_data["collection_size_bytes"]
        if "files_collected" in result_data:
            diagnostic.files_collected = result_data["files_collected"]

        session.commit()

        return {"result": True, "message": "Diagnostic result processed"}
