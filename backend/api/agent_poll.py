# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""HTTP transport for agents whose network will not pass a WebSocket Upgrade.

WHY THIS EXISTS
---------------
The agent normally holds one outbound WebSocket to 443 and everything -- both
directions -- rides that socket.  Some corporate proxies refuse to tunnel it.
Measured against a real HTTP CONNECT proxy that returns 403 to the tunnel
request, the agent gets::

    InvalidProxyStatus: proxy rejected connection: HTTP 403

and has no connection at all.  Not a degraded one: none.  Every command, every
inventory update, every heartbeat is simply undeliverable, and the host is
invisible until somebody changes the proxy policy.

That is the last hole in "outbound 443 and nothing else": the port is right, but
the *protocol* is what gets blocked.

WHAT THIS IS NOT
----------------
Not a second messaging system.  Server and agent already exchange everything
through a durable queue -- ``enqueue_message`` / ``dequeue_messages_for_host`` --
and the WebSocket handler is only a transport that drains it.  So this endpoint
drains the same queue over an ordinary POST.  A message does not know or care
which transport carried it, which is what keeps the two paths from drifting into
different behaviour.

Registration already happens over plain REST, so an agent that cannot open a
WebSocket can still enrol and then poll: the whole lifecycle stays on ordinary
HTTP that any proxy will pass.

WHY POST AND NOT SSE OR LONG-POLL-BY-DEFAULT
--------------------------------------------
A plain request/response POST is the thing proxies are least likely to interfere
with -- no Upgrade, no chunked streaming, no long-lived socket to time out.
``max_wait`` allows a *bounded* long poll for latency, but it is optional and
capped: a proxy that kills idle connections at 30s degrades to more frequent
short polls rather than to a broken agent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.db import get_db
from backend.security.communication_security import websocket_security
from backend.utils.log_sanitize import scrub
from backend.utils.verbosity_logger import get_logger
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_manager import server_queue_manager

logger = get_logger(__name__)

router = APIRouter()

# How many queued commands one poll may carry.  Bounded so a host that has been
# offline for a week cannot produce a single multi-megabyte response that a
# proxy then truncates.
MAX_MESSAGES_PER_POLL = 50

# Upper bound on the caller's long-poll hint.  Kept under the 30s idle timeout
# common to corporate proxies and load balancers: exceeding it turns a working
# poll into a connection the middlebox silently drops.
MAX_WAIT_SECONDS = 25


class PolledMessage(BaseModel):
    """One agent -> server message, in the same envelope the WebSocket carries."""

    message_type: str
    data: Dict[str, Any] = Field(default_factory=dict)
    message_id: Optional[str] = None


class PollRequest(BaseModel):
    host_id: str
    messages: List[PolledMessage] = Field(default_factory=list)
    max_wait: int = 0


class PollResponse(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    poll_interval: int = 5


def _authenticated_host_id(
    request: Request,
    payload: PollRequest,
    authorization: Optional[str],
) -> str:
    """Validate the agent's connection token and return the host it may act as.

    The same token the WebSocket path issues via ``/agent/auth`` -- deliberately,
    so switching transport does not mean switching trust model. An agent that
    can open a WebSocket can poll, and vice versa, with identical authority.
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail=_("Missing agent connection token"))

    client_host = request.client.host if request.client else "unknown"
    if not websocket_security.validate_connection_token(token, client_host):
        logger.warning(
            "Agent poll rejected: invalid connection token from %s for host %s",
            scrub(client_host),
            scrub(payload.host_id),
        )
        raise HTTPException(
            status_code=401, detail=_("Invalid or expired connection token")
        )

    return payload.host_id


@router.post("/agent/poll", response_model=PollResponse)
async def agent_poll(
    request: Request,
    payload: PollRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> PollResponse:
    """Exchange queued messages in both directions over one ordinary POST.

    Inbound messages are enqueued exactly as the WebSocket handler enqueues
    them, so the existing inbound processor handles them without knowing which
    transport delivered them. Outbound messages are dequeued and marked sent,
    the same bookkeeping ``outbound_processor`` performs.
    """
    host_id = _authenticated_host_id(request, payload, authorization)

    # --- agent -> server -------------------------------------------------
    accepted = 0
    for message in payload.messages:
        try:
            server_queue_manager.enqueue_message(
                message_type=message.message_type,
                message_data=message.data,
                direction=QueueDirection.INBOUND,
                host_id=host_id,
                db=db,
            )
            accepted += 1
        except Exception:  # pylint: disable=broad-except
            # Loud, with context: a silently dropped inbound message is
            # indistinguishable from an agent that never sent it.
            logger.exception(
                "Could not enqueue polled message %s from host %s",
                scrub(message.message_type),
                scrub(host_id),
            )

    # --- server -> agent -------------------------------------------------
    pending = server_queue_manager.dequeue_messages_for_host(
        host_id=host_id,
        direction=QueueDirection.OUTBOUND,
        limit=MAX_MESSAGES_PER_POLL,
        db=db,
    )

    outbound: List[Dict[str, Any]] = []
    for queued in pending:
        outbound.append(
            {
                "message_id": queued.message_id,
                "message_type": queued.message_type,
                "data": queued.message_data,
            }
        )
        server_queue_manager.mark_sent(queued.message_id, db=db)

    if accepted or outbound:
        logger.debug(
            "Agent poll for host %s: accepted %d, returned %d",
            scrub(host_id),
            accepted,
            len(outbound),
        )

    # Ask a busy agent back sooner. A queue that still has work should not wait
    # out the idle interval before draining the rest.
    interval = 1 if len(outbound) >= MAX_MESSAGES_PER_POLL else 5
    return PollResponse(messages=outbound, poll_interval=interval)
