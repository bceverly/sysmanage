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
