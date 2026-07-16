# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Child host listing handlers.

Public handler dispatches to the Pro+ ``child_host_handlers_engine`` when
loaded.  Without the engine, child-host management is not available —
the handler returns a ``feature_not_licensed`` error.  Child hosts are a
Pro+ feature.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.licensing.module_loader import module_loader

logger = logging.getLogger(__name__)


_ENGINE_CODE = "child_host_handlers_engine"


def _engine_handler(name: str):
    """Return the engine's handler with this name, or None if engine not loaded."""
    engine = module_loader.get_module(_ENGINE_CODE)
    if engine is None:
        return None
    return getattr(engine, name, None)


def _proplus_required_response() -> Dict[str, Any]:
    """Standard error returned when child-host messages arrive without Pro+ loaded."""
    return {
        "message_type": "error",
        "error_type": "feature_not_licensed",
        "message": _("Child host management requires a Professional+ license."),
        "data": {},
    }


async def handle_child_hosts_list_update(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; otherwise return Pro+ required."""
    engine_fn = _engine_handler("handle_child_hosts_list_update")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("Pro+ engine handler raised: %s", exc)
    return _proplus_required_response()
