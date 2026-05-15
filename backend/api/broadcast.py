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

Architecture: this endpoint enqueues one OUTBOUND queue row per
matching host (via ``QueueOperations``) and returns the number of
rows enqueued.  The websocket outbound processor is responsible for
actually delivering each envelope to its agent — agents that are
offline at enqueue time will receive the envelope when they next
reconnect.  This endpoint must never call ``connection_manager``'s
direct send/broadcast helpers; those bypass the queue and break
ordering + offline resilience.
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
from backend.websocket.messages import MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()


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

    # Resolve target set + enqueue.  We pull the matching host_ids in
    # a single DB query, then enqueue one OUTBOUND row per host.  The
    # outbound processor delivers each row independently — offline
    # agents pick theirs up on reconnect.
    started = time.monotonic()
    target_host_ids = _resolve_broadcast_targets(db, tag_uuid, request.platform)
    if tag_uuid is not None and request.platform:
        target_filter = f"tag:{tag_uuid}+platform:{request.platform}"
    elif tag_uuid is not None:
        target_filter = f"tag:{tag_uuid}"
    elif request.platform:
        target_filter = f"platform:{request.platform}"
    else:
        target_filter = "all"

    delivered = _enqueue_envelope_for_hosts(db, target_host_ids, envelope)
    elapsed_ms = (time.monotonic() - started) * 1000.0

    logger.info(
        "Broadcast %s action=%s filter=%s enqueued=%d elapsed=%.1fms",
        broadcast_id,
        sanitize_log(request.broadcast_action),
        sanitize_log(target_filter),
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


def _resolve_broadcast_targets(
    db: Session, tag_uuid: Optional[uuid.UUID], platform: Optional[str]
) -> list:
    """Return the list of active Host.id values matching the requested
    tag/platform filters.  ``None`` for both filters means "all active
    hosts".  All filtering is one DB query — no in-memory iteration over
    websocket connections, since broadcasts must reach agents that are
    currently offline too (they pick the queued envelope up on reconnect).
    """
    query = db.query(models.Host.id).filter(models.Host.active.is_(True))
    if tag_uuid is not None:
        query = query.join(
            models.HostTag, models.HostTag.host_id == models.Host.id
        ).filter(models.HostTag.tag_id == tag_uuid)
    if platform:
        query = query.filter(models.Host.platform == platform)
    return [row[0] for row in query.all()]


def _enqueue_envelope_for_hosts(
    db: Session, host_ids: list, envelope: Dict[str, Any]
) -> int:
    """Enqueue one OUTBOUND row of ``envelope`` per host_id.  Returns the
    number of rows actually persisted (a single failure does not abort
    the rest of the fan-out)."""
    enqueued = 0
    for host_id in host_ids:
        try:
            queue_ops.enqueue_message(
                message_type=MessageType.BROADCAST.value,
                message_data=envelope,
                direction=QueueDirection.OUTBOUND,
                host_id=str(host_id),
                db=db,
            )
            enqueued += 1
        except Exception as enqueue_error:
            logger.error(
                "Failed to enqueue broadcast for host %s: %s",
                host_id,
                enqueue_error,
            )
    if enqueued:
        # ``enqueue_message`` only flushes when given a session; commit is
        # the caller's responsibility — without it the rows roll back when
        # FastAPI's get_db() finalizes the request.
        db.commit()
    return enqueued
