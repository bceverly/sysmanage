"""
This module houses Graylog-related API routes for hosts in SysManage.
"""

import logging
import uuid
from typing import Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.websocket.messages import CommandMessage, CommandType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
logger = logging.getLogger(__name__)
queue_ops = QueueOperations()


@router.get("/host/{host_id}/graylog_attachment")
async def get_host_graylog_attachment(
    host_id: str, current_user: str = Depends(get_current_user)
):
    """
    Get Graylog attachment status for a host.

    Returns the Graylog attachment information including:
    - is_attached: whether the host is forwarding logs to Graylog
    - target_hostname: hostname of the Graylog server
    - target_ip: IP address of the Graylog server
    - mechanism: how logs are being forwarded (syslog_tcp, syslog_udp, gelf_tcp, windows_sidecar)
    - port: port number
    - detected_at: when this was first detected
    - updated_at: when this was last updated
    """
    try:
        from backend.persistence.models import GraylogAttachment

        logger.info("Fetching Graylog attachment for host %s", host_id)

        session_local = sessionmaker(
            bind=db.get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        with session_local() as session:
            # Convert string UUID to UUID object if needed
            host_uuid = uuid.UUID(host_id)

            # Get the Graylog attachment for this host
            graylog_attachment = (
                session.query(GraylogAttachment)
                .filter(GraylogAttachment.host_id == host_uuid)
                .first()
            )

            if graylog_attachment:
                logger.info("Found Graylog attachment for host %s", host_id)
                return graylog_attachment.to_dict()

            # Return default "not attached" status if no record exists
            logger.info(
                "No Graylog attachment found for host %s, returning default", host_id
            )
            return {
                "is_attached": False,
                "target_hostname": None,
                "target_ip": None,
                "mechanism": None,
                "port": None,
                "detected_at": None,
                "updated_at": None,
            }

    except ValueError as e:
        logger.error("Invalid host ID format for %s: %s", host_id, e)
        raise HTTPException(status_code=400, detail="Invalid host ID format") from e
    except Exception as e:
        logger.error(
            "Error fetching Graylog attachment for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch Graylog attachment status: {str(e)}",
        ) from e


@router.post("/host/{host_id}/attach_to_graylog", dependencies=[Depends(JWTBearer())])
async def attach_host_to_graylog(
    host_id: str,
    request: Dict = Body(...),
    current_user: str = Depends(get_current_user),
):
    """
    Queue a command to attach a host to Graylog using the specified mechanism.

    Args:
        host_id: ID of the host to attach
        request: Graylog attachment configuration (mechanism, graylog_server, port)
        current_user: Current authenticated user

    Returns:
        Success message with command ID
    """
    session_local = sessionmaker(
        bind=db.get_engine(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    with session_local() as session:
        # Get host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Validate host approval status
        validate_host_approval_status(host)

        # Create command message
        command_data = {
            "mechanism": request.get("mechanism"),
            "graylog_server": request.get("graylog_server"),
            "port": request.get("port"),
        }

        command_message = CommandMessage(
            command_type=CommandType.ATTACH_TO_GRAYLOG, parameters=command_data
        )

        # Queue the message for outbound delivery
        try:
            logger.info(
                "About to queue Graylog attachment command for host %s using mechanism %s",
                host_id,
                request.get("mechanism"),
            )
            logger.info("Command message dict: %s", command_message.to_dict())
            queue_ops.enqueue_message(
                message_type="command",
                message_data=command_message.to_dict(),
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                db=session,
            )
            logger.info(
                "Successfully queued Graylog attachment command for host %s using mechanism %s",
                host_id,
                request.get("mechanism"),
            )
            # Commit the session to persist the queued message
            session.commit()
            logger.info(
                "Successfully committed Graylog attachment command for host %s",
                host_id,
            )
        except Exception as e:
            logger.error(
                "Failed to queue Graylog attachment command for host %s: %s",
                host_id,
                str(e),
                exc_info=True,
            )
            raise

        return {
            "success": True,
            "message": _("Graylog attachment command queued successfully"),
        }
