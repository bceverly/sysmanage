"""
Pro+ schedule-dispatch glue between Cython engines and the OSS message queue.

The Pro+ ``automation_engine`` and ``fleet_engine`` modules export
``start_schedule_dispatcher`` coroutines that take a ``dispatch_fn``
callback.  When a cron-scheduled execution / bulk operation fires inside
the engine, the engine creates the corresponding record (ScriptExecution
or BulkOperation) and hands it to the callback.  The callbacks here turn
those records into APPLY_DEPLOYMENT_PLAN messages and queue them via the
existing ``QueueOperations`` infrastructure so the agent's existing
generic-deployment handler can run them.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.licensing.module_loader import module_loader
from backend.persistence import db, models
from backend.websocket.messages import CommandType, Message, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
_queue_ops = QueueOperations()

# In-memory correlation map: message_id (the queue ID echoed back by the
# agent in command_result.command_id) -> (engine_name, primary_id, host_id).
#   engine_name: "automation_engine" | "fleet_engine"
#   primary_id : execution_id (automation) or op_id (fleet)
#   host_id    : the target host this dispatch was for
#
# Phase 5 ships this in-process; Phase 5.x maintenance can promote to a DB
# table once we have a use-case that survives a process restart (today the
# engine in-memory registries don't survive restarts either, so a process
# restart loses everything across the board — same blast radius).
_CORRELATIONS: Dict[str, Tuple[str, str, str]] = {}
_CORRELATIONS_LOCK = threading.Lock()


def _register_correlation(
    message_id: str, engine: str, primary_id: str, host_id: str
) -> None:
    with _CORRELATIONS_LOCK:
        _CORRELATIONS[message_id] = (engine, primary_id, host_id)


def _pop_correlation(message_id: str) -> Optional[Tuple[str, str, str]]:
    with _CORRELATIONS_LOCK:
        return _CORRELATIONS.pop(message_id, None)


def correlation_count() -> int:
    """Test helper: how many correlations are currently registered."""
    with _CORRELATIONS_LOCK:
        return len(_CORRELATIONS)


def _enqueue_apply_plan(host_id: str, plan: dict, timeout: int = 300) -> str:
    """
    Wrap a deploy plan in an APPLY_DEPLOYMENT_PLAN message and queue it.

    Returns the message_id assigned by the queue, which the agent echoes
    back in its command_result.command_id field — used for correlating
    results to the dispatched execution / bulk op.
    """
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
            "parameters": {"plan": plan},
            "timeout": timeout,
        },
    )
    session_local = db.get_session_local()
    with session_local() as session:
        return _queue_ops.enqueue_message(
            message_type="command",
            message_data=message.to_dict(),
            direction=QueueDirection.OUTBOUND,
            host_id=str(host_id),
            db=session,
        )


# ---------------------------------------------------------------------------
# Automation engine dispatch
# ---------------------------------------------------------------------------


def queue_automation_execution(execution, schedule) -> None:
    """
    Dispatch a scheduler-triggered ScriptExecution to its target hosts.

    Called by ``automation_engine.start_schedule_dispatcher`` for each
    scheduled execution that fires.  Builds a per-host APPLY_DEPLOYMENT_PLAN
    using the engine's own ``build_script_command_plan`` factory and queues
    one message per host_id.
    """
    automation_engine = module_loader.get_module("automation_engine")
    if automation_engine is None:
        logger.warning(
            "queue_automation_execution called but automation_engine isn't loaded"
        )
        return

    # Pull the script's shell + timeout off the saved-script registry to
    # build the deploy plan (the execution carries the rendered content
    # but not the metadata).
    script = automation_engine.get_script(execution.script_id)
    if script is None:
        logger.warning(
            "Scheduled execution %s references unknown script %s",
            execution.id,
            execution.script_id,
        )
        return

    plan = automation_engine.build_script_command_plan(
        execution.rendered_content,
        script.shell,
        script.timeout_seconds,
    )

    queued = 0
    for host_result in execution.host_results:
        try:
            msg_id = _enqueue_apply_plan(
                host_result.host_id, plan, script.timeout_seconds
            )
            _register_correlation(
                msg_id,
                "automation_engine",
                execution.id,
                host_result.host_id,
            )
            queued += 1
        except Exception as exc:
            logger.warning(
                "Failed to queue scheduled execution %s for host %s: %s",
                execution.id,
                host_result.host_id,
                exc,
            )
    logger.info(
        "Scheduled execution %s (script=%s schedule=%s) queued on %d host(s)",
        execution.id,
        execution.script_id,
        schedule.name,
        queued,
    )


# ---------------------------------------------------------------------------
# Fleet engine dispatch
# ---------------------------------------------------------------------------


# Operation types that translate into a deployment plan we can queue.
# Anything not in this set is logged-and-skipped from the scheduler path
# (real-time API callers can still use those op types via the explicit
# /v1/fleet/bulk endpoint).
_QUEUEABLE_OPS = {
    "run_script",
    "deploy_file",
    "service_control",
    "install_package",
    "remove_package",
    "reboot",
    "shutdown",
}


def build_host_provider(db_maker: Callable) -> Callable[[], List[Any]]:
    """
    Build the synchronous host_provider callable the fleet scheduler needs.

    Returns a 0-arg callable that opens a fresh DB session each time and
    returns the live list of Hosts.  The fleet engine resolves selectors
    against this list to pick which hosts a scheduled op fires on.
    """

    def _provider():
        # `db_maker` is `get_db` (a generator dependency).  Pull one session
        # out of it just like the Pro+ background tasks for vuln/health do.
        gen = db_maker()
        try:
            session = next(gen)
        except (StopIteration, TypeError):
            return []
        try:
            return session.query(models.Host).all()
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    return _provider


def queue_fleet_bulk_op(operation, schedule) -> None:
    """
    Dispatch a scheduler-triggered BulkOperation to its target hosts.

    Called by ``fleet_engine.start_schedule_dispatcher`` for each scheduled
    fleet op that fires.  Routes to the OSS ``bulk_op_planner`` to expand
    the op into per-host plans, then queues each plan as APPLY_DEPLOYMENT_PLAN.
    """
    if operation.operation_type not in _QUEUEABLE_OPS:
        logger.info(
            "Scheduled fleet op '%s' uses op_type '%s' which the queueing "
            "dispatcher doesn't currently handle; skipping",
            schedule.name,
            operation.operation_type,
        )
        return

    from backend.services.bulk_op_planner import expand_bulk_operation

    try:
        per_host = expand_bulk_operation(
            operation.operation_type,
            list(operation.target_host_ids),
            dict(operation.parameters),
        )
    except Exception as exc:
        logger.warning(
            "Failed to expand scheduled fleet op '%s': %s",
            schedule.name,
            exc,
        )
        return

    queued = 0
    for host_id, plan in per_host:
        try:
            msg_id = _enqueue_apply_plan(host_id, plan)
            _register_correlation(msg_id, "fleet_engine", operation.id, host_id)
            queued += 1
        except Exception as exc:
            logger.warning(
                "Failed to queue scheduled fleet op %s for host %s: %s",
                operation.id,
                host_id,
                exc,
            )
    logger.info(
        "Scheduled fleet op %s (%s, schedule=%s) queued on %d host(s)",
        operation.id,
        operation.operation_type,
        schedule.name,
        queued,
    )


# ---------------------------------------------------------------------------
# Result routing — call from handle_command_result
# ---------------------------------------------------------------------------


def _extract_command_outcome(result_data: dict) -> Dict[str, Any]:
    """Flatten the agent's apply_deployment_plan payload into one dict.

    Returns keys: status, returncode, stdout, stderr, error.
    """
    success = bool(result_data.get("success", False))
    inner = result_data.get("result") or {}
    cmd_results = (inner.get("results") or {}).get("commands") or []
    first = cmd_results[0] if cmd_results else {}
    returncode = first.get("returncode")
    if returncode is None:
        returncode = 0 if success else -1
    return {
        "status": "succeeded" if success else "failed",
        "returncode": returncode,
        "stdout": first.get("stdout") or "",
        "stderr": first.get("stderr") or "",
        "error": result_data.get("error"),
    }


def _apply_engine_result(
    engine: Any,
    engine_name: str,
    primary_id: str,
    host_id: str,
    outcome: Dict[str, Any],
) -> None:
    """Dispatch the flattened outcome to the appropriate engine update fn."""
    if engine_name == "automation_engine":
        engine.update_execution_host_result(
            primary_id,
            host_id,
            outcome["status"],
            returncode=outcome["returncode"],
            stdout=outcome["stdout"],
            stderr=outcome["stderr"],
            error=outcome["error"],
        )
    elif engine_name == "fleet_engine":
        engine.update_bulk_host_result(
            primary_id,
            host_id,
            outcome["status"],
            message=outcome["error"] or f"exit {outcome['returncode']}",
        )


def route_proplus_command_result(command_id: str, result_data: dict) -> bool:
    """
    Route a command_result message to the right Pro+ engine, if it
    correlates to a Pro+ dispatch.

    Args:
        command_id: The original message_id (echoed by the agent in
                    command_result.command_id).
        result_data: The full command_result payload from the agent
                     (top-level keys: success, result, error, exit_code).

    Returns:
        True if the result was routed to a Pro+ engine; False if no
        correlation exists (caller should continue with normal handling).
    """
    correlation = _pop_correlation(command_id)
    if correlation is None:
        return False

    engine_name, primary_id, host_id = correlation
    engine = module_loader.get_module(engine_name)
    if engine is None:
        logger.warning(
            "Pro+ command_result correlation found for %s but engine '%s' is no "
            "longer loaded; result lost",
            command_id,
            engine_name,
        )
        return True

    outcome = _extract_command_outcome(result_data)
    try:
        _apply_engine_result(engine, engine_name, primary_id, host_id, outcome)
    except Exception as exc:
        logger.warning(
            "Failed to update Pro+ engine '%s' result for %s/%s: %s",
            engine_name,
            primary_id,
            host_id,
            exc,
        )
    return True
