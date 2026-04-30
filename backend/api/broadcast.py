"""
Fleet broadcast API (Phase 8.5).

One endpoint:

  POST /api/broadcast

Sends a single envelope to every connected agent (or every agent
matching a tag).  Common payloads:

  - ``broadcast_action="refresh_inventory"``  — operator-triggered
    "ping every agent for fresh inventory" without per-host requests.
  - ``broadcast_action="banner"`` + ``message`` — display a banner /
    notification on the agent host.

The actual semantic of the broadcast is interpreted by the agent's
broadcast handler.  This endpoint is the dispatcher.

Performance contract:  for fleets up to 100 hosts the broadcast must
complete inside 5 seconds (Phase 8 exit criterion).  Implementation
fans out via ``connection_manager`` which iterates the in-memory
connection table — no per-host DB queries on the hot path.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import MessageType

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/broadcast",
    tags=["broadcast"],
    dependencies=[Depends(JWTBearer())],
)


class BroadcastRequest(BaseModel):
    """The minimum payload an operator needs to broadcast.  Most
    fields are optional;  the agent's broadcast handler picks what
    it needs based on ``broadcast_action``."""

    broadcast_action: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="What the agent should do — e.g. 'refresh_inventory', 'banner'",
    )
    message: Optional[str] = Field(
        None, max_length=4000, description="Optional human-readable text payload"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form parameters the agent's handler may use",
    )
    tag_id: Optional[str] = Field(
        None,
        description="If supplied, broadcast only to hosts with this tag; "
        "otherwise to every connected agent",
    )
    platform: Optional[str] = Field(
        None,
        description="Optional platform filter (e.g. 'Linux'); applied AFTER "
        "tag_id when both are supplied",
    )


class BroadcastResponse(BaseModel):
    broadcast_id: str
    broadcast_action: str
    delivered_count: int
    elapsed_ms: float
    target_filter: str  # "all" | "tag:<uuid>" | "platform:<name>" | combo


def _parse_tag_uuid_or_400(value: Optional[str]) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=_("Invalid tag_id: %s") % value
        ) from exc


@router.post("", response_model=BroadcastResponse)
async def broadcast_to_fleet(
    request: BroadcastRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Fan out one broadcast envelope to every matching connected agent.

    Returns the number of agents that successfully received the
    message and how long the broadcast took (operators care about
    both — delivered_count<expected means agents are offline,
    elapsed_ms>5s means the dispatch path needs investigation)."""
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))

    tag_uuid = _parse_tag_uuid_or_400(request.tag_id)
    if tag_uuid is not None:
        # Verify the tag exists — bad UUIDs that happen to parse but
        # don't reference an actual tag would silently broadcast to
        # nobody, which is a worse failure mode than a 404.
        tag_exists = db.query(models.Tag.id).filter(models.Tag.id == tag_uuid).first()
        if not tag_exists:
            raise HTTPException(status_code=404, detail=_("Tag not found"))

    broadcast_id = str(uuid.uuid4())
    envelope = {
        "message_type": MessageType.BROADCAST.value,
        "broadcast_id": broadcast_id,
        "broadcast_action": request.broadcast_action,
        "message": request.message,
        "parameters": request.parameters,
        "issued_by": current_user,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Resolve target set + dispatch.  ``connection_manager`` is the
    # single hot-path:  it iterates active_connections in-memory.
    started = time.monotonic()
    if tag_uuid is not None and request.platform:
        # Combined filter: tag first, then platform.  Two passes is fine —
        # the typical fleet size means this is bounded by O(N) connections.
        delivered = await _broadcast_tag_and_platform(
            tag_uuid, request.platform, envelope
        )
        target_filter = f"tag:{tag_uuid}+platform:{request.platform}"
    elif tag_uuid is not None:
        delivered = await connection_manager.broadcast_to_tagged(tag_uuid, envelope)
        target_filter = f"tag:{tag_uuid}"
    elif request.platform:
        delivered = await connection_manager.broadcast_to_platform(
            request.platform, envelope
        )
        target_filter = f"platform:{request.platform}"
    else:
        delivered = await connection_manager.broadcast_to_all(envelope)
        target_filter = "all"
    elapsed_ms = (time.monotonic() - started) * 1000.0

    logger.info(
        "Broadcast %s action=%s filter=%s delivered=%d elapsed=%.1fms",
        broadcast_id,
        request.broadcast_action,
        target_filter,
        delivered,
        elapsed_ms,
    )

    AuditService.log(
        db=db,
        action_type=ActionType.AGENT_MESSAGE,
        entity_type=EntityType.HOST,
        entity_id=broadcast_id,
        entity_name=request.broadcast_action,
        description=_("Broadcast '%s' delivered to %d host(s) (filter=%s, %.0fms)")
        % (request.broadcast_action, delivered, target_filter, elapsed_ms),
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
        details={
            "broadcast_id": broadcast_id,
            "broadcast_action": request.broadcast_action,
            "delivered_count": delivered,
            "elapsed_ms": elapsed_ms,
            "target_filter": target_filter,
        },
    )

    return BroadcastResponse(
        broadcast_id=broadcast_id,
        broadcast_action=request.broadcast_action,
        delivered_count=delivered,
        elapsed_ms=round(elapsed_ms, 2),
        target_filter=target_filter,
    )


async def _broadcast_tag_and_platform(
    tag_uuid: uuid.UUID, platform: str, envelope: dict
) -> int:
    """Helper: deliver to agents that satisfy BOTH a tag filter AND a
    platform filter.  Resolves the tag's hostnames once, then iterates
    active connections in memory and checks both predicates."""
    from sqlalchemy.orm import sessionmaker  # local import
    from backend.persistence import db as persistence_db

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=persistence_db.get_engine()
    )
    with session_local() as session:
        tagged_host_ids = {
            row[0]
            for row in session.query(models.HostTag.host_id)
            .filter(models.HostTag.tag_id == tag_uuid)
            .all()
        }
        tagged_fqdns = {
            str(host.fqdn).lower()
            for host in session.query(models.Host)
            .filter(models.Host.id.in_(tagged_host_ids))
            .all()
        }
    if not tagged_fqdns:
        return 0

    delivered = 0
    failed_agents = []
    for agent_id, connection in connection_manager.active_connections.items():
        if (connection.hostname or "").lower() not in tagged_fqdns:
            continue
        if connection.platform != platform:
            continue
        if await connection.send_message(envelope):
            delivered += 1
        else:
            failed_agents.append(agent_id)
    for aid in failed_agents:
        connection_manager.disconnect(aid)
    return delivered
