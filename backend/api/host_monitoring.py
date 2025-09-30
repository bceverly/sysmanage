"""
Host monitoring endpoints for certificates, roles, and service control.
This module handles endpoints related to monitoring aspects of hosts.
"""

import logging
from datetime import timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import db, models
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import create_command_message

router = APIRouter()
logger = logging.getLogger(__name__)


class ServiceControlRequest(BaseModel):
    """
    Service control request model for starting, stopping, or restarting services.
    """

    action: str  # "start", "stop", or "restart"
    services: List[str]  # List of service names to control


@router.get("/host/{host_id}/certificates", dependencies=[Depends(JWTBearer())])
async def get_host_certificates(host_id: str):
    """
    Get SSL certificates collected from a host.
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

        # Get certificates for this host
        certificates = (
            session.query(models.HostCertificate)
            .filter(models.HostCertificate.host_id == host_id)
            .order_by(
                models.HostCertificate.not_after.asc()
            )  # Order by expiration date
            .all()
        )

        # Convert to dictionary format for JSON response
        certificate_data = []
        for cert in certificates:
            certificate_data.append(
                {
                    "id": cert.id,
                    "certificate_name": cert.certificate_name,
                    "subject": cert.subject,
                    "issuer": cert.issuer,
                    "not_before": (
                        cert.not_before.replace(tzinfo=timezone.utc).isoformat()
                        if cert.not_before
                        else None
                    ),
                    "not_after": (
                        cert.not_after.replace(tzinfo=timezone.utc).isoformat()
                        if cert.not_after
                        else None
                    ),
                    "serial_number": cert.serial_number,
                    "fingerprint_sha256": cert.fingerprint_sha256,
                    "is_ca": cert.is_ca,
                    "key_usage": cert.key_usage,
                    "file_path": cert.file_path,
                    "collected_at": (
                        cert.collected_at.replace(tzinfo=timezone.utc).isoformat()
                        if cert.collected_at
                        else None
                    ),
                    "is_expired": cert.is_expired,
                    "days_until_expiry": cert.days_until_expiry,
                    "common_name": cert.common_name,
                }
            )

        return {
            "host_id": host_id,
            "fqdn": host.fqdn,
            "total_certificates": len(certificate_data),
            "certificates": certificate_data,
        }


@router.post(
    "/host/{host_id}/request-certificates-collection",
    dependencies=[Depends(JWTBearer())],
)
async def request_certificates_collection(host_id: str):
    """
    Request an agent to collect SSL certificates from the system.
    This sends a message via WebSocket to the agent requesting certificate collection.
    """
    logger.info("CERTIFICATE COLLECTION: Endpoint called for host_id: %s", host_id)

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            logger.warning("CERTIFICATE COLLECTION: Host not found: %s", host_id)
            raise HTTPException(status_code=404, detail=_("Host not found"))

        logger.info(
            "CERTIFICATE COLLECTION: Found host %s (fqdn: %s)", host_id, host.fqdn
        )

        validate_host_approval_status(host)

        # Create command message for certificate collection request
        command_message = create_command_message(
            command_type="collect_certificates", parameters={}
        )

        logger.info(
            "CERTIFICATE COLLECTION: Created command message: %s", command_message
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        logger.info("CERTIFICATE COLLECTION: WebSocket send result: %s", success)

        if not success:
            logger.warning(
                "CERTIFICATE COLLECTION: Agent not connected for host: %s", host_id
            )
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        logger.info(
            "CERTIFICATE COLLECTION: Successfully requested certificate collection for host: %s",
            host_id,
        )
        return {"result": True, "message": _("Certificate collection requested")}


@router.get("/host/{host_id}/roles", dependencies=[Depends(JWTBearer())])
async def get_host_roles(host_id: str):
    """
    Get server roles detected on a host.
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

        # Get roles for this host
        roles = (
            session.query(models.HostRole)
            .filter(models.HostRole.host_id == host_id)
            .order_by(models.HostRole.role.asc(), models.HostRole.package_name.asc())
            .all()
        )

        # Convert to dictionary format for JSON response
        role_data = []
        for role in roles:
            role_data.append(
                {
                    "id": role.id,
                    "role": role.role,
                    "package_name": role.package_name,
                    "package_version": role.package_version,
                    "service_name": role.service_name,
                    "service_status": role.service_status,
                    "is_active": role.is_active,
                    "detected_at": (
                        role.detected_at.replace(tzinfo=timezone.utc).isoformat()
                        if role.detected_at
                        else None
                    ),
                    "updated_at": (
                        role.updated_at.replace(tzinfo=timezone.utc).isoformat()
                        if role.updated_at
                        else None
                    ),
                }
            )

        return {
            "host_id": host_id,
            "fqdn": host.fqdn,
            "total_roles": len(role_data),
            "roles": role_data,
        }


@router.post(
    "/host/{host_id}/request-roles-collection",
    dependencies=[Depends(JWTBearer())],
)
async def request_roles_collection(host_id: str):
    """
    Request an agent to collect server roles from the system.
    This sends a message via WebSocket to the agent requesting role collection.
    """
    logger.info("ROLE COLLECTION: Endpoint called for host_id: %s", host_id)

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

        # Create command message for role collection request
        command_message = create_command_message(
            command_type="collect_roles", parameters={}
        )

        logger.info("ROLE COLLECTION: Created command message: %s", command_message)

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        logger.info("ROLE COLLECTION: WebSocket send result: %s", success)

        if not success:
            logger.error("ROLE COLLECTION: Failed to send command to host %s", host_id)
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        logger.info(
            "ROLE COLLECTION: Successfully requested role collection for host: %s",
            host_id,
        )

        return {"result": True, "message": _("Role collection requested")}


@router.post("/host/{host_id}/service-control", dependencies=[Depends(JWTBearer())])
async def control_services(host_id: str, request: ServiceControlRequest):
    """
    Control services on a host (start, stop, restart).
    This sends a command via WebSocket to the agent to control the specified services.
    """
    logger.info(
        "SERVICE CONTROL: Endpoint called for host_id: %s, action: %s, services: %s",
        host_id,
        request.action,
        request.services,
    )

    # Validate action
    if request.action not in ["start", "stop", "restart"]:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid action. Must be 'start', 'stop', or 'restart'"),
        )

    # Validate services list
    if not request.services:
        raise HTTPException(status_code=400, detail=_("No services specified"))

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

        # Check if host is running in privileged mode
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=403,
                detail=_("Host must be running in privileged mode for service control"),
            )

        # Create command message for service control
        command_message = create_command_message(
            command_type="service_control",
            parameters={"action": request.action, "services": request.services},
        )

        logger.info("SERVICE CONTROL: Created command message: %s", command_message)

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        logger.info("SERVICE CONTROL: WebSocket send result: %s", success)

        if not success:
            logger.error("SERVICE CONTROL: Failed to send command to host %s", host_id)
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        logger.info(
            "SERVICE CONTROL: Successfully requested %s for services %s on host: %s",
            request.action,
            request.services,
            host_id,
        )

        return {
            "result": True,
            "message": _("Service {} requested for {} services").format(
                request.action, len(request.services)
            ),
            "action": request.action,
            "services": request.services,
        }
