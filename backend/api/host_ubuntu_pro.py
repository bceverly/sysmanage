# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Ubuntu Pro management endpoints for hosts.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import get_host_by_id
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence.partitions import get_request_engine
from backend.persistence.tenant_context import get_active_tenant
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
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
    current_user=Depends(require_authenticated_user),
):
    """
    Attach Ubuntu Pro subscription to a host using the provided token.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the host command/queue data routes to
    # the active tenant's engine via get_request_engine().
    if not current_user.has_role(SecurityRoles.ATTACH_UBUNTU_PRO):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: ATTACH_UBUNTU_PRO role required"),
        )

    token = request.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail=_("Ubuntu Pro token is required"))

    # Capture the active tenant in the request's async context so the data
    # session routes to the right engine (inert in collapsed/single-tenant mode).
    tenant_id = get_active_tenant()
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=get_request_engine(tenant_id)
    )

    with session_local() as db_session:
        try:
            # Get host to verify it exists
            host = get_host_by_id(host_id)

            # Prepare command message for Ubuntu Pro attach
            command_message = create_command_message(
                command_type="ubuntu_pro_attach",
                parameters={"token": token},
            )

            # Enqueue the message for processing by message processor
            queue_message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_message,
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
async def detach_ubuntu_pro(
    host_id: str, current_user=Depends(require_authenticated_user)
):
    """
    Detach Ubuntu Pro subscription from a host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the host command/queue data routes to
    # the active tenant's engine via get_request_engine().
    if not current_user.has_role(SecurityRoles.DETACH_UBUNTU_PRO):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: DETACH_UBUNTU_PRO role required"),
        )

    # Capture the active tenant in the request's async context so the data
    # session routes to the right engine (inert in collapsed/single-tenant mode).
    tenant_id = get_active_tenant()
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=get_request_engine(tenant_id)
    )

    with session_local() as db_session:
        try:
            # Get host to verify it exists
            host = get_host_by_id(host_id)

            # Prepare command message for Ubuntu Pro detach
            command_message = create_command_message(
                command_type="ubuntu_pro_detach",
                parameters={},
            )

            # Enqueue the message for processing by message processor
            queue_message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_message,
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

    # Capture the active tenant in the request's async context so the data
    # session routes to the right engine (inert in collapsed/single-tenant mode).
    tenant_id = get_active_tenant()
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=get_request_engine(tenant_id)
    )

    with session_local() as db_session:
        try:
            # Get host to verify it exists
            host = get_host_by_id(host_id)

            # Prepare command message for Ubuntu Pro service enable
            command_message = create_command_message(
                command_type="ubuntu_pro_enable_service",
                parameters={"service": service},
            )

            # Enqueue the message for processing by message processor
            queue_message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_message,
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

    # Capture the active tenant in the request's async context so the data
    # session routes to the right engine (inert in collapsed/single-tenant mode).
    tenant_id = get_active_tenant()
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=get_request_engine(tenant_id)
    )

    with session_local() as db_session:
        try:
            # Get host to verify it exists
            host = get_host_by_id(host_id)

            # Prepare command message for Ubuntu Pro service disable
            command_message = create_command_message(
                command_type="ubuntu_pro_disable_service",
                parameters={"service": service},
            )

            # Enqueue the message for processing by message processor
            queue_message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_message,
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
