# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Send a Pro+ automation_engine execution to its hosts.

Moved out of ``proplus_dispatch`` (which re-exports it).  A host whose agent
runs only approved scripts (``host.script_approval_required``) is held until
the execution is approved; the engine's ``plan_dispatch`` decides which hosts
to send now and opens the approval, and approving calls this again
(``dispatch_approved``), which sends only what was held, with the approval's
id in the plan -- the agent refuses a script plan without it.  An engine too
old to have ``plan_dispatch`` sends every host, as before.

The helpers are read from ``proplus_dispatch`` at call time, so tests that
patch them there keep working.
"""

import logging
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)


def _approval_hosts(host_ids: Iterable[str]) -> List[str]:
    """The hosts among ``host_ids`` whose agent requires approval for scripts,
    each read from the database that holds it."""
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence import models  # noqa: PLC0415
    from backend.persistence.partitions import (  # noqa: PLC0415
        get_request_engine,
        tenant_engine_for_host,
    )

    found = []
    for host_id in host_ids:
        engine = tenant_engine_for_host(host_id) or get_request_engine()
        with sessionmaker(bind=engine)() as session:
            host = session.query(models.Host).filter(models.Host.id == host_id).first()
            if host is not None and getattr(host, "script_approval_required", False):
                found.append(str(host_id))
    return found


def _decide(engine, execution) -> Dict[str, Any]:
    """``{"send": [...], "held": [...], "approval_id": ...}`` for this pass."""
    plan_dispatch = getattr(engine, "plan_dispatch", None)
    host_ids = [str(hr.host_id) for hr in execution.host_results]
    if plan_dispatch is None:  # an engine from before host approval
        return {"send": host_ids, "held": [], "approval_id": None}
    return plan_dispatch(execution.id, approval_hosts=_approval_hosts(host_ids))


def queue_automation_execution(execution, schedule) -> None:
    """
    Dispatch a ScriptExecution to its target hosts.

    Called by ``automation_engine.start_schedule_dispatcher`` for each
    scheduled execution that fires, and by ``dispatch_approved`` (with
    ``schedule`` None) when an approval releases held hosts.  Builds a
    per-host APPLY_DEPLOYMENT_PLAN with the engine's own
    ``build_script_command_plan`` and queues one message per host sent.
    """
    from backend.services import proplus_dispatch as pd  # noqa: PLC0415

    automation_engine = pd.module_loader.get_module("automation_engine")
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

    decision = _decide(automation_engine, execution)
    plan = automation_engine.build_script_command_plan(
        execution.rendered_content,
        script.shell,
        script.timeout_seconds,
        decision["approval_id"],
    )

    queued = 0
    for host_id in decision["send"]:
        try:
            msg_id = pd._enqueue_apply_plan(  # pylint: disable=protected-access
                host_id, plan, script.timeout_seconds
            )
            pd._register_correlation(  # pylint: disable=protected-access
                msg_id, "automation_engine", execution.id, host_id
            )
            queued += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to queue scheduled execution %s for host %s: %s",
                execution.id,
                host_id,
                exc,
            )
    logger.info(
        "Execution %s (script=%s schedule=%s) queued on %d host(s), %d held "
        "for approval",
        execution.id,
        execution.script_id,
        getattr(schedule, "name", None),
        queued,
        len(decision["held"]),
    )
