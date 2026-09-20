# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Building an apply-profile command from a STORED profile (Phase 20.1).

Lives in services, not in the API, because two callers need it: the apply
endpoint (an operator pressing a button) and the assignment tick (a cron
schedule coming due). Those two must produce byte-identical commands -- a
scheduled apply that differs from a manual one is a bug nobody finds until a
fleet drifts, and the scheduled path is the one nobody exercises by hand.

Raises ``DispatchError`` rather than ``HTTPException``: a tick has no request
to fail, and importing the API layer from a service would be a circular
import besides. The API translates it to a status code.
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional

from backend.i18n import _
from backend.services import config_mgmt_engines as engines
from backend.services import config_mgmt_spec_shim as spec_shim

logger = logging.getLogger(__name__)


class DispatchError(Exception):
    """A stored profile cannot be turned into a runnable command.

    Carries a ``status`` so the API can map it without re-deciding: 400 for a
    body the operator can fix, 503 for a licensed engine whose module is not
    loaded on this server.
    """

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def profile_body(profile) -> Dict[str, Any]:
    """The profile body in the shape this engine's agent expects.

    DSC bodies are stored as the JSON text the author typed, so they are
    parsed here: a bad stored body becomes an error naming the profile rather
    than an opaque failure on the host hours later.
    """
    if profile.engine != engines.DSC:
        return {"playbook": profile.content}

    try:
        parsed = json.loads(profile.content)
    except ValueError as exc:
        raise DispatchError(
            _("Profile '%s' does not contain valid JSON") % profile.name
        ) from exc
    if not isinstance(parsed, list):
        raise DispatchError(
            _("Profile '%s' must contain a JSON array of DSC resources") % profile.name
        )
    return {"resources": parsed}


def parameters_for(
    profile, check_mode: bool, timeout: Optional[int] = None
) -> Dict[str, Any]:
    """The command parameters the agent will receive for a stored profile.

    ``profile_id`` and ``profile_name`` are always included: the agent echoes
    them back on the result, and that echo is the only way the recorded run
    links to the profile that produced it.
    """
    parameters: Dict[str, Any] = {
        "profile": profile_body(profile),
        "check_mode": bool(check_mode),
        "profile_id": str(profile.id),
        "profile_name": profile.name,
    }

    if engines.requires_license(profile.engine):
        # A licensed engine is driven by a SPEC the Pro+ module builds -- the
        # agent deliberately does not know how to run Puppet/Salt/Chef. No
        # spec means there is nothing to dispatch.
        spec = spec_shim.build_licensed_spec(
            profile.engine,
            profile.content,
            check_mode=bool(check_mode),
            timeout=timeout,
        )
        if spec is None:
            raise DispatchError(
                _(
                    "The configuration management engine is licensed but not "
                    "available on this server"
                ),
                status=503,
            )
        parameters["spec"] = spec

    if timeout:
        parameters["timeout"] = timeout
    return parameters


def queue_apply(db_session, host_id, parameters: Dict[str, Any]) -> str:
    """Queue one APPLY_CONFIG_PROFILE command and return its command id.

    WHY THIS IS A FUNCTION AND NOT SEVEN LINES AT EACH CALL SITE
    -----------------------------------------------------------
    It has to generate ONE id and use it for BOTH the envelope and the queue
    row. The agent echoes the ENVELOPE's ``message_id`` back as ``command_id``
    on its result, so a queue row carrying a different id -- which is exactly
    what ``enqueue_message`` generates when you do not pass one -- leaves the
    result uncorrelatable, and config-profile results were silently dropped
    for precisely that reason until a real round trip found it on 2026-08-28.

    That is a trap you fall into by writing the obvious code, so by Phase 20.2
    the same seven lines and the same warning comment had been pasted into
    three places. Fleet jobs would have made it four, and a fleet job NEEDS the
    id returned -- ``ConfigJobTarget.command_id`` is the only thing that closes
    a target when its result lands. One implementation, returning the id.

    Raises whatever ``enqueue_message`` raises, including
    ``UnsupportedCapabilityError`` for a host that has not advertised
    config-management support (Phase 19). Callers decide whether that is a
    failure or an ordinary skip; this function deliberately does not, because
    it is an error for an operator pressing a button and a routine outcome for
    a fleet job walking four thousand hosts.
    """
    # Imported here rather than at module scope: the queue package pulls in the
    # websocket stack, and this module is imported by the assignment tick,
    # which must stay importable in a plain unit test.
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
            "command_type": CommandType.APPLY_CONFIG_PROFILE,
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
