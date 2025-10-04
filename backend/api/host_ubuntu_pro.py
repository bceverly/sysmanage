"""
Ubuntu Pro management endpoints for hosts.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import get_host_by_id
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    server_queue_manager,
)

router = APIRouter()


class UbuntuProAttachRequest(BaseModel):
    """Request model for Ubuntu Pro attach."""

    token: str

    class Config:
        extra = "forbid"


class UbuntuProServiceRequest(BaseModel):
    """
    Request model for Ubuntu Pro service management.
    """

    service: str

    class Config:
        extra = "forbid"


@router.post("/host/{host_id}/ubuntu-pro/attach", dependencies=[Depends(JWTBearer())])
async def attach_ubuntu_pro(
    host_id: str,
    request: UbuntuProAttachRequest,
    current_user=Depends(get_current_user),
):
    """
    Attach Ubuntu Pro subscription to a host using the provided token.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )
    with session_local() as session:
        # Check if user has permission to attach Ubuntu Pro
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.ATTACH_UBUNTU_PRO):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: ATTACH_UBUNTU_PRO role required"),
            )

    token = request.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail=_("Ubuntu Pro token is required"))

    with session_local() as db_session:
        try:
            # Get host to verify it exists
            host = get_host_by_id(host_id)

            # Prepare command data for Ubuntu Pro attach
            command_data = {
                "command_type": "ubuntu_pro_attach",
                "parameters": {"token": token},
            }

            # Enqueue the message for processing by message processor
            queue_message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_data,
                direction=QueueDirection.OUTBOUND,
                host_id=host.id,
                priority=Priority.HIGH,
                db=db_session,
            )

            # Commit the database session to persist the enqueued message
            db_session.commit()

            return {
                "result": True,
                "message": _("Ubuntu Pro attach requested"),
                "queue_id": queue_message_id,
            }

        except HTTPException:
            raise
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=500,
                detail=_("Failed to request Ubuntu Pro attach: %s") % str(e),
            ) from e


@router.post("/host/{host_id}/ubuntu-pro/detach", dependencies=[Depends(JWTBearer())])
async def detach_ubuntu_pro(host_id: str, current_user=Depends(get_current_user)):
    """
    Detach Ubuntu Pro subscription from a host.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to detach Ubuntu Pro
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.DETACH_UBUNTU_PRO):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DETACH_UBUNTU_PRO role required"),
            )

    with session_local() as db_session:
        try:
            # Get host to verify it exists
            host = get_host_by_id(host_id)

            # Prepare command data for Ubuntu Pro detach
            command_data = {"command_type": "ubuntu_pro_detach", "parameters": {}}

            # Enqueue the message for processing by message processor
            queue_message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_data,
                direction=QueueDirection.OUTBOUND,
                host_id=host.id,
                priority=Priority.HIGH,
                db=db_session,
            )

            # Commit the database session to persist the enqueued message
            db_session.commit()

            return {
                "result": True,
                "message": _("Ubuntu Pro detach requested"),
                "queue_id": queue_message_id,
            }

        except HTTPException:
            raise
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=500,
                detail=_("Failed to request Ubuntu Pro detach: %s") % str(e),
            ) from e


@router.post(
    "/host/{host_id}/ubuntu-pro/service/enable", dependencies=[Depends(JWTBearer())]
)
async def enable_ubuntu_pro_service(host_id: str, request: UbuntuProServiceRequest):
    """
    Enable Ubuntu Pro service on a host.
    """
    service = request.service.strip()
    if not service:
        raise HTTPException(status_code=400, detail=_("Service name is required"))

    from sqlalchemy.orm import sessionmaker

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as db_session:
        try:
            # Get host to verify it exists
            host = get_host_by_id(host_id)

            # Prepare command data for Ubuntu Pro service enable
            command_data = {
                "command_type": "ubuntu_pro_enable_service",
                "parameters": {"service": service},
            }

            # Enqueue the message for processing by message processor
            queue_message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_data,
                direction=QueueDirection.OUTBOUND,
                host_id=host.id,
                priority=Priority.HIGH,
                db=db_session,
            )

            # Commit the database session to persist the enqueued message
            db_session.commit()

            return {
                "result": True,
                "message": _("Ubuntu Pro service enable requested"),
                "queue_id": queue_message_id,
            }

        except HTTPException:
            raise
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=500,
                detail=_("Failed to request Ubuntu Pro service enable: %s") % str(e),
            ) from e


@router.post(
    "/host/{host_id}/ubuntu-pro/service/disable", dependencies=[Depends(JWTBearer())]
)
async def disable_ubuntu_pro_service(host_id: str, request: UbuntuProServiceRequest):
    """
    Disable Ubuntu Pro service on a host.
    """
    service = request.service.strip()
    if not service:
        raise HTTPException(status_code=400, detail=_("Service name is required"))

    from sqlalchemy.orm import sessionmaker

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as db_session:
        try:
            # Get host to verify it exists
            host = get_host_by_id(host_id)

            # Prepare command data for Ubuntu Pro service disable
            command_data = {
                "command_type": "ubuntu_pro_disable_service",
                "parameters": {"service": service},
            }

            # Enqueue the message for processing by message processor
            queue_message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_data,
                direction=QueueDirection.OUTBOUND,
                host_id=host.id,
                priority=Priority.HIGH,
                db=db_session,
            )

            # Commit the database session to persist the enqueued message
            db_session.commit()

            return {
                "result": True,
                "message": _("Ubuntu Pro service disable requested"),
                "queue_id": queue_message_id,
            }

        except HTTPException:
            raise
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=500,
                detail=_("Failed to request Ubuntu Pro service disable: %s") % str(e),
            ) from e
