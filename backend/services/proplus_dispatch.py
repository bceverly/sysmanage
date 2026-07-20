# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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

# This module is the central correlation/result-routing hub for every
# Pro+ engine — splitting it would just spread the result-router and
# its helpers across files that always have to be read together.

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.utils.verbosity_logger import sanitize_log

# Re-exported here under the legacy private name so the sister test module
# ``test_proplus_dispatch_parsers`` doesn't have to chase the rename.
from backend.services.proplus_capability_parser import (
    parse_capability_probe_stdout as _parse_capability_probe_stdout,
)

# VM/child-host stdout parsers + engine-path result-apply handlers live in
# sibling modules (extracted to keep this file under pylint's max-module-lines);
# re-imported here under their original private names so callers and the sister
# test module ``test_proplus_dispatch_parsers`` see no change.
from backend.services.airgap_result_handlers import (  # pylint: disable=unused-import
    _apply_airgap_ingest_result,
    _apply_airgap_run_result,
)
from backend.services.child_host_output_parsers import (  # pylint: disable=unused-import
    _enrich_bhyve_child_with_meta,
    _find_top_level_brace_spans,
    _iter_top_level_json_chunks,
    _normalize_status,
    _parse_bhyve_meta_section,
    _parse_bhyve_section,
    _parse_kvm_section,
    _parse_list_child_hosts_stdout,
    _parse_lxd_section,
    _parse_vmm_section,
    _parse_wsl_section,
    _split_section_blocks,
    _try_load_json_object,
)
from backend.services.child_host_result_handlers import (  # pylint: disable=unused-import
    _apply_child_host_create_result,
    _apply_child_host_delete_result,
    _apply_child_host_lifecycle_result,
    _apply_child_host_op_result,
    _apply_child_host_update_agent_result,
    _outcome_error_text,
)

# Repository-mirroring engine-path result handlers also live in a sibling module
# (this file is the correlation/result-routing hub; the mirror-specific row
# updates are bulky enough to carve out).  Re-imported under their original
# private names so ``_SIMPLE_RESULT_HANDLERS`` and any test references are
# unchanged.  ``_apply_repo_mirror_op_result`` is the entry the router table
# points at; the rest are re-exported for completeness / test access.
from backend.services.repo_mirror_result_handlers import (  # pylint: disable=unused-import
    _apply_mirror_setup_check,
    _apply_mirror_setup_install,
    _apply_mirror_sync_status,
    _apply_repo_mirror_op_result,
    _parse_setup_check_stdout,
    _post_restore_outcome,
    _post_snapshot_outcome,
    _queue_followup_setup_check,
)
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


def enqueue_apply_plan(host_id: str, plan: dict, timeout: int = 300) -> str:
    """Public alias of ``_enqueue_apply_plan`` for cross-module use
    (e.g., the Pro+ router-factory dispatch_plan_fn parameter).  The
    internal private name is retained for the existing callers and
    their test fixtures."""
    return _enqueue_apply_plan(host_id, plan, timeout)


def _enqueue_apply_plan(host_id: str, plan: dict, timeout: int = 300) -> str:
    """
    Wrap a deploy plan in an APPLY_DEPLOYMENT_PLAN message and queue it.

    Returns the message_id assigned by the queue.  CRITICAL: this same
    UUID is used for BOTH the queue row id AND the inner Message
    payload's ``message_id`` field — that's the value the agent echoes
    back in ``command_result.command_id``, and the value the correlation
    map is keyed on.  Prior to this we let ``Message.__init__`` mint its
    own UUID, which produced two different IDs and silently dropped
    every Pro+ engine result on the floor.
    """
    import uuid as _uuid

    shared_id = str(_uuid.uuid4())
    message = Message(
        message_type=MessageType.COMMAND,
        message_id=shared_id,
        data={
            "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
            "parameters": {"plan": plan},
            "timeout": timeout,
        },
    )
    # Route the OUTBOUND command to the host's TENANT database so (a) the
    # per-tenant outbound processor delivers it and (b) enqueue_message's
    # host-existence check runs against the database that actually holds the
    # host.  Forcing the bootstrap session here (the old behaviour) raised
    # "Host ID not found" for a tenant-bound host, which the engine-dispatch
    # callers swallow into a 502.  Prefer the host→tenant index (works in any
    # context, including background dispatch); fall back to the request's
    # active-tenant engine (the middleware ContextVar) so a tenant-scoped UI
    # request still routes correctly before the index is populated.  Both
    # collapse to the bootstrap engine in single-tenant mode, so this is inert
    # there.
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence.partitions import (  # noqa: PLC0415
        get_request_engine,
        tenant_engine_for_host,
    )
    from backend.persistence.tenant_context import (  # noqa: PLC0415
        get_active_tenant,
    )

    # Resolve the database that actually holds this host so the OUTBOUND command
    # lands in its per-tenant queue and enqueue_message's host-existence check
    # passes:
    #   * Request context (a tenant is active): route to the request's ACTIVE
    #     tenant — the SAME database the handler read the host from (get_host
    #     uses request_sessionmaker / get_request_engine, which honors this
    #     ContextVar).  This is authoritative for "where the user is acting"; the
    #     host→tenant index can lag or disagree with where the data actually is.
    #   * Background context (no active tenant — scheduler/queue processor):
    #     resolve via the host→tenant index, since there is no request tenant.
    # Both collapse to the bootstrap engine in single-tenant mode, so this is
    # inert there.
    active_tenant = get_active_tenant()
    if active_tenant:
        engine = get_request_engine()
    else:
        engine = tenant_engine_for_host(host_id) or get_request_engine()
    logger.debug(
        "proplus dispatch: routing OUTBOUND for host %s via %s (active_tenant=%s)",
        sanitize_log(host_id),
        "active-tenant" if active_tenant else "host-index",
        sanitize_log(active_tenant),
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with session_local() as session:
        message_id = _queue_ops.enqueue_message(
            message_type="command",
            message_data=message.to_dict(),
            direction=QueueDirection.OUTBOUND,
            host_id=str(host_id),
            message_id=shared_id,
            db=session,
        )
        # When a session is provided to ``enqueue_message`` it only
        # flushes; commit is the caller's responsibility.  Without this
        # commit the queued row is rolled back when ``with`` exits and
        # the message silently disappears.
        session.commit()
        return message_id


def register_child_host_correlation(
    message_id: str, child_id: str, action: str, host_id: str
) -> None:
    """Register an engine-path child host operation for result-routing.

    Stored as a regular correlation with engine_name="child_host_op" so the
    routing in ``route_proplus_command_result`` can dispatch it to the
    HostChild updater.  ``action`` is encoded into ``primary_id`` as
    ``"<action>:<child_id>"`` so the result handler knows whether this
    was create / start / stop / restart / delete / update_agent.
    """
    _register_correlation(
        message_id,
        "child_host_op",
        f"{action}:{child_id}",
        host_id,
    )


def register_host_op_correlation(message_id: str, action: str, host_id: str) -> None:
    """Register an engine-path parent-host operation (init/disable/probe).

    Used for actions where there's no HostChild row to update directly —
    e.g. KVM/bhyve/VMM/LXD init, virtualization capability probes.  On
    completion the result handler can refresh the host's
    ``virtualization_capabilities`` cache and emit an audit-style log
    entry.
    """
    _register_correlation(
        message_id,
        "host_op",
        action,
        host_id,
    )


def register_federation_command_correlation(
    message_id: str, federated_command_id: str, host_id: str
) -> None:
    """Register a coordinator-dispatched federated command for result-routing.

    The site's actuation worker (``federation_actuation_service``) fans a
    federated command out to local agents as normal ``command`` messages;
    each agent's ``command_result`` echoes the queue message_id, which we
    route back to the federation inbox here.  ``primary_id`` carries the
    federated (received-command) id so the per-host outcome aggregates
    against the right inbox row.
    """
    _register_correlation(
        message_id,
        "federation_command",
        federated_command_id,
        host_id,
    )


def register_repo_mirror_correlation(
    message_id: str, action: str, host_id: str, mirror_id: str = ""
) -> None:
    """Register a repository-mirroring engine plan for result-routing.

    The ``primary_id`` encodes ``"<action>:<mirror_id>"`` so the result
    handler knows whether this was a sync / snapshot / restore /
    integrity_check / gc / setup_check / setup_install, and which row
    to update.  ``mirror_id`` is empty for host-level setup_check /
    setup_install operations (those update ``mirror_setup_status``
    keyed by host_id alone).
    """
    _register_correlation(
        message_id,
        "repo_mirror_op",
        f"{action}:{mirror_id}",
        host_id,
    )


def register_airgap_run_correlation(
    message_id: str, stage: str, run_id: str, host_id: str
) -> None:
    """Register an air-gap collection-run plan for result-routing.

    ``stage`` is the lifecycle phase the plan represents ("mirroring"
    or "building_iso"); the result handler keys off it to decide which
    state transition to apply (MIRRORING → STAGING_COMPLETE vs
    BUILDING_ISO → ISO_BUILT).  ``primary_id`` encodes
    ``"<stage>:<run_id>"``.
    """
    _register_correlation(
        message_id,
        "airgap_run",
        f"{stage}:{run_id}",
        host_id,
    )


def register_airgap_ingest_correlation(
    message_id: str, stage: str, run_id: str, host_id: str
) -> None:
    """Register a repository-side ingestion plan for result-routing.

    ``stage`` is the ingestion phase the plan represents ("mount" or
    "copy"); the result handler keys off it to decide which transition
    to apply (mount → verify-then-VERIFIED, copy → COMPLETE).
    ``primary_id`` encodes ``"<stage>:<run_id>"``.
    """
    _register_correlation(
        message_id,
        "airgap_ingest",
        f"{stage}:{run_id}",
        host_id,
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

    Returns keys: status, returncode, stdout, stderr, error, commands.

    ``stdout``/``stderr`` are the FIRST command's streams (preserved for
    handlers that just need a one-shot stderr).  ``commands`` is the
    full per-command list so action-specific handlers can attribute
    errors to the actually-failed step and parse stats from a
    later-in-the-plan command (e.g. rsync ``--stats`` output for
    snapshot size/file-count).
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
        "commands": cmd_results,
    }


def _best_failure_text(outcome: Dict[str, Any]) -> str:
    """Pick the most useful error string from a failed outcome.

    The agent's plan executor stops on the first hard failure, so the
    failed step is the LAST entry in ``commands`` with ``success: False``.
    Use that command's stderr in preference to the first command's
    stderr (which is often empty when the first command succeeded and
    a later one failed).  Falls back to ``outcome["error"]`` then a
    static "no error message returned" sentinel.
    """
    for cmd in reversed(outcome.get("commands") or []):
        if cmd.get("success") is False:
            stderr = (cmd.get("stderr") or "").strip()
            if stderr:
                return stderr
            description = cmd.get("description") or " ".join(cmd.get("argv") or [])
            rc = cmd.get("returncode")
            return f"{description} exited {rc} with no stderr"
    return outcome.get("stderr") or outcome.get("error") or "no error message returned"


# rsync --stats output is human-readable but two lines are reliably
# parseable for ints:
#   Number of files: <total>,<details>
#   Total file size: <bytes> bytes
# ``--stats`` uses thousands-separator commas in newer rsync, so we
# strip them before int() parsing.
_RSYNC_STATS_FILES_RE = re.compile(r"Number of files:\s*([\d,]+)")
_RSYNC_STATS_BYTES_RE = re.compile(r"Total file size:\s*([\d,]+)\s+bytes")


def _parse_rsync_stats(stdout: str) -> Dict[str, Optional[int]]:
    """Pull file count + total bytes out of rsync ``--stats`` output."""
    out: Dict[str, Optional[int]] = {"file_count": None, "size_bytes": None}
    if not stdout:
        return out
    m = _RSYNC_STATS_FILES_RE.search(stdout)
    if m:
        out["file_count"] = int(m.group(1).replace(",", ""))
    m = _RSYNC_STATS_BYTES_RE.search(stdout)
    if m:
        out["size_bytes"] = int(m.group(1).replace(",", ""))
    return out


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


# Capability-probe parsing lives in ``proplus_capability_parser`` (imported
# at the top of this module under the legacy ``_parse_capability_probe_stdout``
# name).  Splitting it out keeps this file under pylint's max-module-lines.


def _apply_list_child_hosts_result(host_id: str, outcome: Dict[str, Any]) -> None:
    """Reuse the legacy ``handle_child_hosts_list_update`` reconciler.

    Parses the sectioned engine plan stdout into the ``child_hosts``
    array shape the legacy handler expects, then calls it with a stub
    connection so the same row-by-row reconciliation runs (insert new,
    update existing, mark missing as stopped, etc.).
    """
    children = _parse_list_child_hosts_stdout(outcome.get("stdout") or "")

    # pylint: disable=import-outside-toplevel
    import asyncio

    from backend.api.handlers.child_host.listing import (
        handle_child_hosts_list_update,
    )
    from backend.persistence import db as _db

    # Synthesize what the legacy handler expects.
    fake_message = {
        "success": True,
        "result": {
            "success": True,
            "child_hosts": children,
            "count": len(children),
        },
    }

    class _StubConnection:  # pylint: disable=too-few-public-methods
        host_id = ""

    stub = _StubConnection()
    stub.host_id = host_id

    session_local = _db.get_session_local()
    with session_local() as session:
        try:
            asyncio.run(handle_child_hosts_list_update(session, stub, fake_message))
        except RuntimeError:
            # Already inside a running event loop — schedule on a new loop.
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    handle_child_hosts_list_update(session, stub, fake_message)
                )
            finally:
                loop.close()
        except Exception as exc:
            logger.warning(
                "Failed to apply list_child_hosts result for host %s: %s",
                host_id,
                exc,
            )


def _apply_capability_probe_result(host_id: str, outcome: Dict[str, Any]) -> None:
    """Persist the parsed capability probe result onto the Host row."""
    parsed = _parse_capability_probe_stdout(outcome.get("stdout") or "")

    # pylint: disable=import-outside-toplevel
    from backend.persistence import db as _db
    from backend.persistence.models import Host

    session_local = _db.get_session_local()
    with session_local() as session:
        host = session.query(Host).filter(Host.id == host_id).first()
        if host is None:
            return
        host.virtualization_capabilities = json.dumps(parsed["capabilities"])
        host.virtualization_types = json.dumps(parsed["supported_types"])
        session.commit()


def _apply_host_op_result(action: str, host_id: str, outcome: Dict[str, Any]) -> None:
    """Handle completion of a parent-host engine plan (init/disable/probe).

    On capability probes, parse the sectioned stdout and persist
    directly to ``host.virtualization_capabilities``.  On init/disable/
    modules, fire a follow-up capability probe (which lands back here
    on the probe branch).
    """
    if outcome["status"] != "succeeded":
        logger.info(
            "Host-op %s failed for host %s: %s",
            action,
            host_id,
            outcome["error"] or outcome["stderr"],
        )
        return

    # The capability probe's stdout IS the data — parse and persist directly.
    if action == "check_virtualization_support":
        try:
            _apply_capability_probe_result(host_id, outcome)
        except Exception as exc:
            logger.warning(
                "Failed to apply capability probe result for host %s: %s",
                host_id,
                exc,
            )
        return

    # The list_child_hosts probe parses sectioned stdout into the same
    # shape the legacy handler consumes, then runs the reconciler.
    if action == "list_child_hosts":
        try:
            _apply_list_child_hosts_result(host_id, outcome)
        except Exception as exc:
            logger.warning(
                "Failed to apply list_child_hosts result for host %s: %s",
                host_id,
                exc,
            )
        return

    # For init / enable / disable / modules — fire a follow-up probe via
    # the container_engine plan path.
    _FOLLOWUP_PROBE_ACTIONS = (
        "enable_kvm_modules",
        "disable_kvm_modules",
        "disable_bhyve",
        "enable_wsl",
    )
    if action.startswith("init_") or action in _FOLLOWUP_PROBE_ACTIONS:
        _queue_capability_followup_probe(action, host_id)


def _queue_capability_followup_probe(action: str, host_id: str) -> None:
    """Queue a check_virtualization_support plan after a state-changing
    host op so the capability cache reflects the new state without a
    manual probe."""
    container_engine = module_loader.get_module("container_engine")
    builder = (
        getattr(container_engine, "build_check_virtualization_support_plan", None)
        if container_engine
        else None
    )
    if builder is None:
        return
    try:
        msg_id = enqueue_apply_plan(host_id=str(host_id), plan=builder(), timeout=60)
        register_host_op_correlation(
            msg_id, "check_virtualization_support", str(host_id)
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to queue follow-up capability check after %s on %s: %s",
            action,
            host_id,
            exc,
        )


def _now_naive():
    """Return a naive UTC datetime — matches the column type on every model."""
    from datetime import datetime, timezone as _tz

    return datetime.now(_tz.utc).replace(tzinfo=None)


def _apply_simple_result(handler, engine_name, primary_id, host_id, outcome) -> None:
    """Run a uniform ``_apply_X(primary_id, host_id, outcome)`` result handler,
    swallowing + logging failures so one bad result never breaks routing."""
    try:
        handler(primary_id, host_id, outcome)
    except Exception as exc:
        logger.warning(
            "Failed to apply %s result for %s on host %s: %s",
            engine_name,
            primary_id,
            host_id,
            exc,
        )


def _route_federation_command_result(primary_id, host_id, outcome) -> None:
    """Aggregate a federated command's per-host outcome into the inbox.

    Needs a DB session and a different call shape than the simple
    engine-path handlers, so it's routed separately.
    """
    try:
        from backend.persistence.db import get_db
        from backend.services import federation_actuation_service

        db_session = next(get_db())
        try:
            federation_actuation_service.record_command_host_result(
                db_session,
                primary_id,
                host_id,
                success=(outcome["status"] == "succeeded"),
                detail=_outcome_error_text(outcome, "") or outcome["stdout"][:2000],
            )
        finally:
            db_session.close()
    except Exception as exc:
        logger.warning(
            "Failed to apply federation_command result for %s on host %s: %s",
            primary_id,
            host_id,
            exc,
        )


# engine_name -> uniform ``_apply_X(primary_id, host_id, outcome)`` handler.
# Adding an engine-path correlation kind is a one-line entry here rather
# than another branch in ``route_proplus_command_result``.
_SIMPLE_RESULT_HANDLERS = {
    "child_host_op": _apply_child_host_op_result,
    "host_op": _apply_host_op_result,
    "repo_mirror_op": _apply_repo_mirror_op_result,
    "airgap_run": _apply_airgap_run_result,
    "airgap_ingest": _apply_airgap_ingest_result,
}


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
    outcome = _extract_command_outcome(result_data)

    # Engine-path operations with a uniform result handler — child_host_op
    # / host_op (update the HostChild/parent row), repo_mirror_op (sync /
    # snapshot / restore / ...), airgap_run (mirroring / building_iso) and
    # airgap_ingest (mount / copy).  See ``_SIMPLE_RESULT_HANDLERS``.
    simple_handler = _SIMPLE_RESULT_HANDLERS.get(engine_name)
    if simple_handler is not None:
        _apply_simple_result(simple_handler, engine_name, primary_id, host_id, outcome)
        return True

    # Federated commands fanned out to local agents need a DB session and a
    # different call shape, so they route on their own.
    if engine_name == "federation_command":
        _route_federation_command_result(primary_id, host_id, outcome)
        return True

    # Existing module-loaded engines (automation_engine, fleet_engine).
    engine = module_loader.get_module(engine_name)
    if engine is None:
        logger.warning(
            "Pro+ command_result correlation found for %s but engine '%s' is no "
            "longer loaded; result lost",
            command_id,
            engine_name,
        )
        return True

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
