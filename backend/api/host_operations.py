"""
Host system operations endpoints (reboot, shutdown, software refresh).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import db, models
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import create_command_message

router = APIRouter()


@router.post("/host/refresh/software/{host_id}", dependencies=[Depends(JWTBearer())])
async def refresh_host_software(host_id: str):
    """
    Request software inventory refresh for a specific host.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Create command message for software inventory update
        command_message = create_command_message(
            command_type="update_software_inventory", parameters={}
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        return {"result": True, "message": _("Software inventory update requested")}


@router.post("/host/reboot/{host_id}", dependencies=[Depends(JWTBearer())])
async def reboot_host(host_id: str):
    """
    Request a system reboot for a specific host.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Create command message for system reboot
        command_message = create_command_message(
            command_type="reboot_system", parameters={}
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        return {"result": True, "message": _("System reboot requested")}


@router.post("/host/shutdown/{host_id}", dependencies=[Depends(JWTBearer())])
async def shutdown_host(host_id: str):
    """
    Request a system shutdown for a specific host.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Create command message for system shutdown
        command_message = create_command_message(
            command_type="shutdown_system", parameters={}
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        return {"result": True, "message": _("System shutdown requested")}
