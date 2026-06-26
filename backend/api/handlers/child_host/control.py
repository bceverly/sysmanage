"""
Child host control handlers.

Public handlers dispatch to the Pro+ ``child_host_handlers_engine`` when
loaded.  Without the engine, child-host management is not available —
the handlers return a ``feature_not_licensed`` error.  Child hosts are
a Pro+ feature.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.licensing.module_loader import module_loader

logger = logging.getLogger(__name__)


_ENGINE_CODE = "child_host_handlers_engine"
_ENGINE_RAISED_MSG = "Pro+ engine handler raised: %s"


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


async def handle_child_host_start_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; otherwise return Pro+ required."""
    engine_fn = _engine_handler("handle_child_host_start_result")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(_ENGINE_RAISED_MSG, exc)
    return _proplus_required_response()


async def handle_child_host_stop_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; otherwise return Pro+ required."""
    engine_fn = _engine_handler("handle_child_host_stop_result")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(_ENGINE_RAISED_MSG, exc)
    return _proplus_required_response()


async def handle_child_host_restart_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; otherwise return Pro+ required."""
    engine_fn = _engine_handler("handle_child_host_restart_result")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(_ENGINE_RAISED_MSG, exc)
    return _proplus_required_response()


async def handle_child_host_delete_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; otherwise return Pro+ required."""
    engine_fn = _engine_handler("handle_child_host_delete_result")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(_ENGINE_RAISED_MSG, exc)
    return _proplus_required_response()
