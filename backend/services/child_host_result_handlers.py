# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Child-host (VM) engine-path result-apply handlers.

Extracted from ``backend.services.proplus_dispatch`` to keep that module under
pylint's max-module-lines cap.  Everything here is re-imported back into
``proplus_dispatch`` under its original private name, so the result-router and
its ``_SIMPLE_RESULT_HANDLERS`` table are unchanged.

These handlers translate a flattened engine ``outcome`` dict into HostChild row
updates for create / delete / start / stop / restart / update_agent operations.
``_outcome_error_text`` lives here (rather than in proplus_dispatch) because the
child-host handlers are its primary users; proplus_dispatch re-imports it.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _outcome_error_text(outcome: Dict[str, Any], default: str) -> str:
    """Return the most informative error text from an outcome dict, or ``default``."""
    return outcome["error"] or outcome["stderr"] or default


def _apply_child_host_delete_result(session, child, outcome: Dict[str, Any]) -> None:
    """Engine delete completed: drop the row + cascade linked Host on success,
    mark the row in error on failure."""
    # pylint: disable=import-outside-toplevel
    from backend.persistence.models import Host

    if outcome["status"] == "succeeded":
        # Cascade to linked Host row, mirroring the legacy flow in
        # handle_child_host_delete_result.
        linked_host_id = child.child_host_id
        session.delete(child)
        if linked_host_id:
            linked = session.query(Host).filter(Host.id == linked_host_id).first()
            if linked:
                session.delete(linked)
    else:
        child.status = "error"
        child.error_message = _outcome_error_text(outcome, "delete failed")


def _apply_child_host_create_result(child, outcome: Dict[str, Any]) -> None:
    """Engine create completed: status=running on success (record installed_at
    if first time), status=error on failure."""
    if outcome["status"] == "succeeded":
        child.status = "running"
        child.error_message = None
        if not child.installed_at:
            # pylint: disable=import-outside-toplevel
            from datetime import datetime, timezone

            child.installed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        child.status = "error"
        child.error_message = _outcome_error_text(outcome, "create failed")


def _apply_child_host_lifecycle_result(
    action: str, child, outcome: Dict[str, Any]
) -> None:
    """Engine start/stop/restart completed: update status, clear or set error."""
    if outcome["status"] == "succeeded":
        child.status = "stopped" if action == "stop" else "running"
        child.error_message = None
    else:
        child.error_message = _outcome_error_text(outcome, f"{action} failed")


def _apply_child_host_update_agent_result(child, outcome: Dict[str, Any]) -> None:
    """Engine update_agent completed: no status change, just error_message."""
    if outcome["status"] == "succeeded":
        child.error_message = None
    else:
        child.error_message = _outcome_error_text(outcome, "update_agent failed")


def _apply_child_host_op_result(
    primary_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Update the HostChild row for a completed engine-path child host op.

    ``primary_id`` is ``"<action>:<child_id>"`` (see register_child_host_correlation).
    ``host_id`` is included in log lines so an operator can correlate the
    HostChild update with the originating parent host in audit/diagnostics.
    Action drives what happens on success/failure:

      * ``create`` — succeeded → status="running", clear error_message.
                     failed    → status="error", error_message=<stderr/error>.
      * ``delete`` — succeeded → row deleted (cascades linked Host).
                     failed    → status="error", error_message set.
      * ``start`` / ``stop`` / ``restart`` — succeeded → status="running"
                                              / "stopped" / "running",
                                              error_message cleared.
      * ``update_agent`` — succeeded → no status change, just
                                       error_message cleared.
    """
    if ":" not in primary_id:
        logger.warning(
            "Malformed child_host_op primary_id %s for host %s",
            primary_id,
            host_id,
        )
        return
    action, child_id = primary_id.split(":", 1)

    # pylint: disable=import-outside-toplevel
    from backend.persistence import db as _db
    from backend.persistence.models import HostChild

    session_local = _db.get_session_local()
    with session_local() as session:
        child = session.query(HostChild).filter(HostChild.id == child_id).first()
        if child is None:
            # Child may have been deleted by another path (e.g. listing
            # reconciliation) before this result landed.  Nothing to do.
            return

        if action == "delete":
            _apply_child_host_delete_result(session, child, outcome)
        elif action == "create":
            _apply_child_host_create_result(child, outcome)
        elif action in ("start", "stop", "restart"):
            _apply_child_host_lifecycle_result(action, child, outcome)
        elif action == "update_agent":
            _apply_child_host_update_agent_result(child, outcome)
        else:
            logger.warning(
                "Unknown child_host_op action %s for host %s", action, host_id
            )
            return

        session.commit()
