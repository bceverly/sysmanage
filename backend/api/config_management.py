"""
Configuration management API endpoints for SysManage server.
Allows administrators to push configuration updates to agents.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config.config_push import config_push_manager
from backend.i18n import _
from backend.persistence import db, models
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

router = APIRouter()


class ConfigUpdateRequest(BaseModel):
    """Request model for configuration updates."""

    config_data: Dict[str, Any] = Field(..., description="Configuration data to push")
    target_hostname: Optional[str] = Field(
        None, description="Specific hostname to target"
    )
    target_platform: Optional[str] = Field(
        None, description="Platform to target (Linux, Windows, etc.)"
    )
    push_to_all: bool = Field(False, description="Push to all connected agents")


class LoggingConfigRequest(BaseModel):
    """Request model for logging configuration updates."""

    log_level: str = Field(
        "INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)"
    )
    log_file: Optional[str] = Field(None, description="Log file path")
    target_hostname: Optional[str] = Field(
        None, description="Specific hostname to target"
    )
    push_to_all: bool = Field(False, description="Push to all connected agents")


class WebSocketConfigRequest(BaseModel):
    """Request model for WebSocket configuration updates."""

    ping_interval: int = Field(30, description="Heartbeat interval in seconds")
    reconnect_interval: int = Field(5, description="Reconnection interval in seconds")
    target_hostname: Optional[str] = Field(
        None, description="Specific hostname to target"
    )
    push_to_all: bool = Field(False, description="Push to all connected agents")


class ServerConfigRequest(BaseModel):
    """Request model for server configuration updates."""

    hostname: str = Field(..., description="Server hostname")
    port: int = Field(8000, description="Server port")
    use_https: bool = Field(False, description="Use HTTPS")
    target_hostname: Optional[str] = Field(
        None, description="Specific hostname to target"
    )
    push_to_all: bool = Field(False, description="Push to all connected agents")


@router.post("/config/push", dependencies=[Depends(JWTBearer())])
async def push_configuration(
    request: ConfigUpdateRequest, current_user=Depends(get_current_user)
):
    """
    Push configuration update to agents.
    """
    try:
        # Get user for audit logging
        from sqlalchemy.orm import sessionmaker

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db.get_engine()
        )
        with session_local() as session:
            auth_user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )

            if request.push_to_all:
                results = await config_push_manager.push_config_to_all_agents(
                    request.config_data
                )

                # Log audit entry for config push to all agents
                if auth_user:
                    AuditService.log_update(
                        db=session,
                        entity_type=EntityType.SETTING,
                        entity_name="Agent Configuration (All Agents)",
                        user_id=auth_user.id,
                        username=current_user,
                        details={
                            "target": "all_agents",
                            "config_data": request.config_data,
                            "total_agents": len(results),
                            "successful": sum(
                                1 for success in results.values() if success
                            ),
                        },
                    )

                return {
                    "message": _("Configuration pushed to all agents"),
                    "results": results,
                    "total_agents": len(results),
                    "successful": sum(1 for success in results.values() if success),
                }

            if request.target_hostname:
                success = await config_push_manager.push_config_to_agent(
                    request.target_hostname, request.config_data
                )
                if success:
                    # Log audit entry for config push to specific agent
                    if auth_user:
                        AuditService.log_update(
                            db=session,
                            entity_type=EntityType.SETTING,
                            entity_name=f"Agent Configuration ({request.target_hostname})",
                            user_id=auth_user.id,
                            username=current_user,
                            details={
                                "target": request.target_hostname,
                                "config_data": request.config_data,
                            },
                        )

                    return {
                        "message": _("Configuration pushed successfully"),
                        "target": request.target_hostname,
                    }
                raise HTTPException(
                    status_code=404, detail=_("Agent not found or unreachable")
                )

            if request.target_platform:
                successful_sends = await config_push_manager.push_config_by_platform(
                    request.target_platform, request.config_data
                )

                # Log audit entry for config push by platform
                if auth_user:
                    AuditService.log_update(
                        db=session,
                        entity_type=EntityType.SETTING,
                        entity_name=f"Agent Configuration ({request.target_platform} Platform)",
                        user_id=auth_user.id,
                        username=current_user,
                        details={
                            "target": request.target_platform,
                            "config_data": request.config_data,
                            "successful_sends": successful_sends,
                        },
                    )

                return {
                    "message": _("Configuration pushed to platform agents"),
                    "platform": request.target_platform,
                    "successful_sends": successful_sends,
                }

            raise HTTPException(
                status_code=400,
                detail=_(
                    "Must specify target_hostname, target_platform, or push_to_all"
                ),
            )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Configuration push failed: {str(e)}"
        ) from e


@router.post("/config/logging", dependencies=[Depends(JWTBearer())])
async def update_logging_config(
    request: LoggingConfigRequest, current_user=Depends(get_current_user)
):
    """
    Update logging configuration on agents.
    """
    config_data = config_push_manager.create_logging_config(
        log_level=request.log_level, log_file=request.log_file
    )

    config_request = ConfigUpdateRequest(
        config_data=config_data,
        target_hostname=request.target_hostname,
        push_to_all=request.push_to_all,
    )

    return await push_configuration(config_request, current_user)


@router.post("/config/websocket", dependencies=[Depends(JWTBearer())])
async def update_websocket_config(
    request: WebSocketConfigRequest, current_user=Depends(get_current_user)
):
    """
    Update WebSocket configuration on agents.
    """
    config_data = config_push_manager.create_websocket_config(
        ping_interval=request.ping_interval,
        reconnect_interval=request.reconnect_interval,
    )

    config_request = ConfigUpdateRequest(
        config_data=config_data,
        target_hostname=request.target_hostname,
        push_to_all=request.push_to_all,
    )

    return await push_configuration(config_request, current_user)


@router.post("/config/server", dependencies=[Depends(JWTBearer())])
async def update_server_config(
    request: ServerConfigRequest, current_user=Depends(get_current_user)
):
    """
    Update server connection configuration on agents.
    """
    config_data = config_push_manager.create_server_config(
        hostname=request.hostname, port=request.port, use_https=request.use_https
    )

    config_request = ConfigUpdateRequest(
        config_data=config_data,
        target_hostname=request.target_hostname,
        push_to_all=request.push_to_all,
    )

    return await push_configuration(config_request, current_user)


@router.get("/config/pending", dependencies=[Depends(JWTBearer())])
async def get_pending_configs():
    """
    Get all pending configuration pushes.
    """
    pending_configs = config_push_manager.get_pending_configs()

    return {"pending_configs": pending_configs, "total_pending": len(pending_configs)}


@router.post("/config/acknowledge", dependencies=[Depends(JWTBearer())])
async def acknowledge_config(
    hostname: str, version: int, success: bool, error: Optional[str] = None
):
    """
    Handle configuration acknowledgment from agents.
    This would typically be called internally by the WebSocket handler.
    """
    config_push_manager.handle_config_acknowledgment(hostname, version, success, error)

    return {
        "message": _("Configuration acknowledgment processed"),
        "hostname": hostname,
        "version": version,
        "success": success,
    }
