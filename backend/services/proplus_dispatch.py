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

# pylint: disable=too-many-lines
# This module is the central correlation/result-routing hub for every
# Pro+ engine — splitting it would just spread the result-router and
# its helpers across files that always have to be read together.

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.licensing.module_loader import module_loader
from backend.persistence import db, models

# Re-exported here under the legacy private name so the sister test module
# ``test_proplus_dispatch_parsers`` doesn't have to chase the rename.
from backend.services.proplus_capability_parser import (
    parse_capability_probe_stdout as _parse_capability_probe_stdout,
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
    session_local = db.get_session_local()
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


# Capability-probe parsing lives in ``proplus_capability_parser`` (imported
# at the top of this module under the legacy ``_parse_capability_probe_stdout``
# name).  Splitting it out keeps this file under pylint's max-module-lines.


def _normalize_status(state: str) -> str:
    """Map per-hypervisor state text to the canonical status the legacy
    handler uses (running / stopped / paused / unknown)."""
    s = state.lower().strip()
    if "run" in s or s in ("locked", "active"):
        return "running"
    if "stop" in s or "shut off" in s or "off" in s or s == "exited":
        return "stopped"
    if "paus" in s or "frozen" in s:
        return "paused"
    if not s:
        return "unknown"
    return s


def _split_section_blocks(stdout: str) -> Dict[str, str]:
    """Split sectioned engine plan stdout into ``{section_name: block_text}``."""
    blocks: Dict[str, str] = {}
    current = None
    buf: list = []
    for raw in stdout.splitlines():
        if raw.startswith("===") and raw.rstrip().endswith("==="):
            if current is not None:
                blocks[current] = "\n".join(buf)
            current = raw.strip("=").strip().lower()
            buf = []
            continue
        if current is not None:
            buf.append(raw)
    if current is not None:
        blocks[current] = "\n".join(buf)
    return blocks


def _parse_lxd_section(text: str) -> list:
    """LXD section is JSON from ``lxc list --format json``."""
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    out = []
    for item in data:
        name = item.get("name") or ""
        if not name:
            continue
        out.append(
            {
                "child_name": name,
                "child_type": "lxd",
                "status": _normalize_status(item.get("status") or ""),
                "hostname": name,
                "type": item.get("type") or "container",
                "architecture": item.get("architecture"),
            }
        )
    return out


def _parse_kvm_section(text: str) -> list:
    """``virsh list --all`` returns a table:

     Id   Name      State
    -----------------------
     1    name1     running
     -    name2     shut off
    """
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Id") or line.startswith("---"):
            continue
        # Split into at most 3 fields: Id (number or '-'), Name, State.
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        out.append(
            {
                "child_name": parts[1],
                "child_type": "kvm",
                "status": _normalize_status(parts[2]),
            }
        )
    return out


def _parse_bhyve_section(text: str) -> list:
    """``vm list`` table:

    NAME  DATASTORE  LOADER  CPU  MEMORY  VNC  AUTO  STATE
    myvm  default    uefi    2    2G      -    Yes   Running (12345)
    """
    out = []
    seen_header = False
    for line in text.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if not seen_header:
            if s.lstrip().startswith("NAME"):
                seen_header = True
            continue
        parts = s.split()
        if not parts:
            continue
        # State is the trailing column(s); take the last 1–2 tokens that
        # form a recognizable state word.
        state = parts[-1] if parts else ""
        # vm-bhyve emits "Running (PID)" — the (PID) is parts[-1] if present.
        if state.startswith("(") and len(parts) >= 2:
            state = parts[-2]
        out.append(
            {
                "child_name": parts[0],
                "child_type": "bhyve",
                "status": _normalize_status(state),
            }
        )
    return out


def _find_top_level_brace_spans(text: str) -> List[Tuple[int, int]]:
    """Inclusive ``(start, end)`` index pairs for each balanced top-level ``{...}``."""
    spans: List[Tuple[int, int]] = []
    depth = 0
    start = -1
    for idx, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append((start, idx))
    return spans


def _iter_top_level_json_chunks(text: str):
    """Yield top-level ``{...}`` substrings; splits concatenated JSON documents."""
    for start, end in _find_top_level_brace_spans(text):
        chunk = text[start : end + 1].strip()
        if chunk:
            yield chunk


def _try_load_json_object(chunk: str):
    """Return the parsed dict for ``chunk`` or None on any failure."""
    try:
        obj = json.loads(chunk)
    except (TypeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _parse_bhyve_meta_section(text: str) -> Dict[str, Dict[str, Any]]:
    """Parse the ``===BHYVE_META===`` block.

    Each /vm/metadata/<name>.json file is concatenated into the block,
    one JSON document per file separated by newlines.  We split on the
    document boundary (``}\\n{``-style) by attempting to load each
    JSON object as we encounter ``{ ... }`` blocks.

    Returns a dict keyed by ``vm_name`` with whatever metadata fields
    were present (typically ``hostname``, ``distribution``, ``vm_ip``).
    Malformed entries are silently skipped — listing enrichment is
    best-effort.
    """
    if not text or not text.strip():
        return {}
    metas: Dict[str, Dict[str, Any]] = {}
    for chunk in _iter_top_level_json_chunks(text):
        obj = _try_load_json_object(chunk)
        if obj is None:
            continue
        name = obj.get("vm_name") or ""
        if name:
            metas[name] = obj
    return metas


def _parse_vmm_section(text: str) -> list:
    """``vmctl status`` table:

    ID   PID VCPUS  MAXMEM  CURMEM     TTY        OWNER NAME
     1 12345     2   2.0G   1.0G    /dev/ttyp0     root  myvm
    """
    out = []
    seen_header = False
    for line in text.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if not seen_header:
            if s.lstrip().startswith("ID"):
                seen_header = True
            continue
        parts = s.split()
        if len(parts) < 2:
            continue
        # NAME is the last column; presence in vmctl status implies running.
        name = parts[-1]
        out.append(
            {
                "child_name": name,
                "child_type": "vmm",
                "status": "running",
            }
        )
    return out


def _parse_wsl_section(text: str) -> list:
    """``wsl --list --verbose`` output (UTF-16LE on Windows; agent decodes
    before placing into stdout):

          NAME            STATE           VERSION
        * Ubuntu          Running         2
          Ubuntu-22.04    Stopped         2
    """
    out = []
    seen_header = False
    for line in text.splitlines():
        # WSL output may have BOM / leading whitespace; normalize.
        s = line.strip("﻿").rstrip()
        if not s.strip():
            continue
        if not seen_header:
            if "NAME" in s and "STATE" in s:
                seen_header = True
            continue
        # Strip a leading '*' marker for the default distro
        if s.lstrip().startswith("*"):
            s = s.lstrip().lstrip("*").lstrip()
        parts = s.split()
        if len(parts) < 2:
            continue
        out.append(
            {
                "child_name": parts[0],
                "child_type": "wsl",
                "status": _normalize_status(parts[1]),
            }
        )
    return out


def _enrich_bhyve_child_with_meta(child: dict, meta: dict) -> None:
    """Apply hostname / vm_ip / distribution from a metadata blob to a child row."""
    if meta.get("hostname"):
        child["hostname"] = meta["hostname"]
    if meta.get("vm_ip"):
        child["vm_ip"] = meta["vm_ip"]
    distribution = meta.get("distribution")
    if not distribution:
        return
    child.setdefault("distribution", {})
    if isinstance(child["distribution"], dict):
        child["distribution"]["distribution_name"] = distribution


def _parse_list_child_hosts_stdout(stdout: str) -> list:
    """Parse the sectioned ``build_list_child_hosts_plan`` output into the
    same ``child_hosts`` list shape ``handle_child_hosts_list_update``
    consumes.

    Audit gap fix #2: the ``BHYVE_META`` section enriches bhyve listing
    rows with hostname / distribution / vm_ip read from
    ``/vm/metadata/<name>.json``.  vm-bhyve's ``vm list`` only reports
    name + state; without this, the UI listing for bhyve VMs has no
    hostname or IP columns.
    """
    blocks = _split_section_blocks(stdout)
    children: list = []
    children.extend(_parse_lxd_section(blocks.get("lxd", "")))
    children.extend(_parse_kvm_section(blocks.get("kvm", "")))
    bhyve_children = _parse_bhyve_section(blocks.get("bhyve", ""))
    bhyve_metas = _parse_bhyve_meta_section(blocks.get("bhyve_meta", ""))
    for child in bhyve_children:
        meta = bhyve_metas.get(child["child_name"])
        if meta:
            _enrich_bhyve_child_with_meta(child, meta)
    children.extend(bhyve_children)
    children.extend(_parse_vmm_section(blocks.get("vmm", "")))
    children.extend(_parse_wsl_section(blocks.get("wsl", "")))
    return children


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


def _apply_repo_mirror_op_result(
    primary_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Handle completion of a repository_mirroring_engine plan.

    ``primary_id`` is ``"<action>:<mirror_id>"``.  Action drives which
    OSS row gets updated:

      sync / snapshot / restore / integrity_check / gc
          → update ``mirror_repository.last_sync_status`` /
            ``last_sync_error`` for the named mirror_id.

      setup_check
          → parse the probe stdout (key=value lines) and upsert
            ``mirror_setup_status`` for the host.

      setup_install
          → mark the install as ``succeeded`` / ``failed`` on the
            ``mirror_setup_status`` row, then queue a follow-up
            ``setup_check`` so the UI reflects post-install tool
            presence without a manual refresh.
    """
    if ":" not in primary_id:
        action, mirror_id = primary_id, ""
    else:
        action, mirror_id = primary_id.split(":", 1)

    session_local = db.get_session_local()
    with session_local() as session:
        if action in ("sync", "snapshot", "restore", "integrity_check", "gc"):
            _apply_mirror_sync_status(session, action, mirror_id, outcome)
        elif action == "setup_check":
            _apply_mirror_setup_check(session, host_id, outcome)
        elif action == "setup_install":
            _apply_mirror_setup_install(session, host_id, outcome)
        elif action in ("default_apply", "default_revert"):
            # Phase 10.4.4 — pointing a client host at (or away from)
            # the locally-hosted mirror.  No row update needed on the
            # OSS side since the assignment was committed BEFORE the
            # plan was queued; the result here is informational only.
            # We log success/failure so a future audit-log endpoint
            # can surface it.
            if outcome["status"] != "succeeded":
                logger.warning(
                    "Mirror default %s failed for host %s: %s",
                    action,
                    host_id,
                    outcome["stderr"] or outcome["error"],
                )
        else:
            logger.warning(
                "Unknown repo_mirror_op action %r (mirror_id=%s host_id=%s)",
                action,
                mirror_id,
                host_id,
            )
            return
        session.commit()

    if action == "setup_install" and outcome["status"] == "succeeded":
        _queue_followup_setup_check(host_id, session_local)


def _queue_followup_setup_check(host_id: str, session_local) -> None:
    """Auto-chain a setup_check after a successful install so the card
    reflects the new tool presence.  The follow-up message rides the
    same outbound queue + result-routing path.  Stamp
    ``last_check_message_id`` on the row before returning, or the
    frontend's polling loop (which keys off non-NULL message_id markers)
    sees both flags clear and stops polling before the auto-probe result
    lands."""
    try:
        mirror_engine = module_loader.get_module("repository_mirroring_engine")
        if mirror_engine is None:
            return
        probe_plan = mirror_engine.build_mirror_setup_check_plan()
        msg_id = enqueue_apply_plan(host_id=str(host_id), plan=probe_plan, timeout=60)
        _register_correlation(msg_id, "repo_mirror_op", "setup_check:", str(host_id))
        with session_local() as probe_session:
            row = (
                probe_session.query(models.MirrorSetupStatus)
                .filter(models.MirrorSetupStatus.host_id == host_id)
                .first()
            )
            if row is not None:
                row.last_check_message_id = msg_id
                probe_session.commit()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to queue follow-up setup_check after install on host %s: %s",
            host_id,
            exc,
        )


def _apply_mirror_sync_status(
    session, action: str, mirror_id: str, outcome: Dict[str, Any]
) -> None:
    """Update ``mirror_repository.last_sync_*`` after a sync-family plan."""
    if not mirror_id:
        return
    row = (
        session.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == mirror_id)
        .first()
    )
    if row is None:
        logger.info("Mirror %s no longer exists; dropping %s result", mirror_id, action)
        return
    if outcome["status"] == "succeeded":
        row.last_sync_status = "SUCCESS"
        row.last_sync_error = None
    else:
        row.last_sync_status = "FAILED"
        row.last_sync_error = (
            outcome["stderr"] or outcome["error"] or "no error message returned"
        )[:8000]


_PROBE_TOOL_KEYS = {
    "apt-mirror",
    "apt-mirror2",
    "reposync",
    "createrepo_c",
    "trickle",
    "rsync",
    "curl",
    "sha256sum",
    "xz",
    "gzip",
    "bzip2",
}


def _parse_setup_check_stdout(stdout: str) -> Dict[str, Any]:
    """Parse the probe's ``key=value`` lines into a structured dict.

    Returns ``{"tools": {<tool>: "present"|"missing"}, "platform": str,
    "distro": str}``.  Unknown keys are dropped so a malicious agent
    can't inject arbitrary fields into the JSON column.
    """
    tools: Dict[str, str] = {}
    platform = ""
    distro = ""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key in _PROBE_TOOL_KEYS and value in ("present", "missing"):
            tools[key] = value
        elif key == "platform":
            platform = value[:40]
        elif key == "distro":
            distro = value[:40]
    return {"tools": tools, "platform": platform, "distro": distro}


def _apply_mirror_setup_check(session, host_id: str, outcome: Dict[str, Any]) -> None:
    """Upsert ``mirror_setup_status`` from the probe's stdout."""
    parsed = _parse_setup_check_stdout(outcome["stdout"])
    now = _now_naive()
    row = (
        session.query(models.MirrorSetupStatus)
        .filter(models.MirrorSetupStatus.host_id == host_id)
        .first()
    )
    if row is None:
        row = models.MirrorSetupStatus(host_id=host_id)
        session.add(row)
    row.tools = parsed["tools"]
    row.platform = parsed["platform"] or row.platform
    row.distro = parsed["distro"] or row.distro
    row.last_check_at = now
    row.last_check_message_id = None  # probe completed; clear in-flight marker
    if outcome["status"] == "succeeded":
        row.last_check_error = None
    else:
        row.last_check_error = (
            outcome["stderr"] or outcome["error"] or "probe failed"
        )[:8000]


def _apply_mirror_setup_install(session, host_id: str, outcome: Dict[str, Any]) -> None:
    """Stamp install_status + clear the in-flight marker."""
    now = _now_naive()
    row = (
        session.query(models.MirrorSetupStatus)
        .filter(models.MirrorSetupStatus.host_id == host_id)
        .first()
    )
    if row is None:
        row = models.MirrorSetupStatus(host_id=host_id)
        session.add(row)
    row.last_install_at = now
    row.last_install_message_id = None
    if outcome["status"] == "succeeded":
        row.install_status = "succeeded"
        row.last_install_error = None
    else:
        row.install_status = "failed"
        row.last_install_error = (
            outcome["stderr"] or outcome["error"] or "install failed"
        )[:8000]


def _now_naive():
    """Return a naive UTC datetime — matches the column type on every model."""
    from datetime import datetime, timezone as _tz

    return datetime.now(_tz.utc).replace(tzinfo=None)


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

    # Child-host engine-path operations: update the HostChild row directly.
    if engine_name == "child_host_op":
        try:
            _apply_child_host_op_result(primary_id, host_id, outcome)
        except Exception as exc:
            logger.warning(
                "Failed to apply child_host_op result for %s on host %s: %s",
                primary_id,
                host_id,
                exc,
            )
        return True

    # Parent-host engine-path operations (init/disable/etc.).
    if engine_name == "host_op":
        try:
            _apply_host_op_result(primary_id, host_id, outcome)
        except Exception as exc:
            logger.warning(
                "Failed to apply host_op result for %s on host %s: %s",
                primary_id,
                host_id,
                exc,
            )
        return True

    # Repository-mirroring engine plans (sync / snapshot / restore /
    # integrity_check / gc / setup_check / setup_install).  ``primary_id``
    # is encoded as ``"<action>:<mirror_id>"`` (mirror_id is empty for
    # host-level setup operations).
    if engine_name == "repo_mirror_op":
        try:
            _apply_repo_mirror_op_result(primary_id, host_id, outcome)
        except Exception as exc:
            logger.warning(
                "Failed to apply repo_mirror_op result for %s on host %s: %s",
                primary_id,
                host_id,
                exc,
            )
        return True

    # Existing engines (automation_engine, fleet_engine).
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
