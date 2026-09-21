# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Turn a query pack into a command on a host's queue (Phase 21.1 S4).

Mirrors ``config_mgmt_dispatch``, and for the same hard-won reason: the
envelope's ``message_id`` and the queue row's id must be THE SAME VALUE. The
agent echoes the envelope id back as ``command_id`` on its result, so a queue
row carrying a different id -- which is exactly what ``enqueue_message``
generates when you do not pass one -- leaves the result uncorrelatable. Config
profile results were silently dropped for precisely that reason until a real
round trip found it, so query packs do it right from the start.

WHAT THIS DOES NOT DECIDE
-------------------------
* Which queries a host can answer -- ``query_pack_shim.build_dispatch`` asks
  the licensed engine, which filters against the host's advertised coverage.
* Whether the host can take the command at all -- ``enqueue_message`` already
  refuses a command the host has not advertised (Phase 19), so a build without
  the query-pack handler is refused there rather than by a second rule here
  that could disagree.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from backend.services import agent_capability_service as caps
from backend.services import query_pack_shim as shim

logger = logging.getLogger(__name__)


def host_fact_coverage(host) -> Optional[Dict[str, Any]]:
    """The host's advertised fact coverage, or None if it never advertised.

    ``None`` is a THIRD state and the caller must keep it that way: a host
    that has not told us what it serves has not told us it serves nothing.
    Treating the two alike would filter every query out of every pack for
    every pre-21.1 agent, and the packs would look like they ran.
    """
    report = caps.get_capability_report(host)
    if not report:
        return None
    facts = report.get("facts")
    return facts if isinstance(facts, dict) else None


def build_payload(pack: Dict[str, Any], queries, host) -> Optional[Dict[str, Any]]:
    """The ``run_query_pack`` parameters for this host, or None.

    ``None`` means the licensed engine is not loaded — see the shim. The
    caller must not fall back to dispatching everything: an unfiltered pack
    sends hosts questions they cannot answer, and those come back as ERRORS,
    which is a different and worse claim than "does not serve those tables".
    """
    coverage = host_fact_coverage(host)
    platform = (getattr(host, "platform", None) or "").lower() or None
    return shim.build_dispatch(pack, queries, coverage, platform)


def queue_run(db_session, host_id, parameters: Dict[str, Any]) -> str:
    """Queue one RUN_QUERY_PACK command and return its command id."""
    # Imported here rather than at module scope: the queue package pulls in
    # the websocket stack, and this module is imported by the tick, which must
    # stay importable in a plain unit test.
    from backend.websocket.messages import (  # noqa: PLC0415
        CommandType,
        Message,
        MessageType,
    )
    from backend.websocket.queue_enums import QueueDirection  # noqa: PLC0415
    from backend.websocket.queue_operations import QueueOperations  # noqa: PLC0415

    command_id = str(uuid.uuid4())
    command = Message(
        message_id=command_id,
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.RUN_QUERY_PACK,
            "parameters": parameters,
        },
    )
    QueueOperations().enqueue_message(
        message_type="command",
        message_id=command_id,
        message_data=command.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host_id),
        db=db_session,
    )
    return command_id
