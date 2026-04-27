"""
Free-tier (open-source) bulk operation planner.

Open-source SysManage supports basic single-host operations.  For convenience,
this planner expands a "do operation X on hosts [a, b, c]" request into one
deploy plan per host, returning the per-host (host_id, plan) tuples that the
caller dispatches via the existing per-host queueing infrastructure.

This is deliberately SIMPLE:
  * No persistence (no BulkOperation record, no per-host result tracking).
  * No batching, no rolling rollouts, no failure thresholds.
  * No host-selector DSL — caller passes an explicit host_ids list.

Pro+ licensees get the richer engine in
sysmanage-professional-plus/module-source/fleet_engine which adds:
  * Persisted BulkOperation records with per-host status tracking
  * Host groups with parent/child hierarchies + dynamic-criteria membership
  * Rolling deployments with batched rollout windows + failure thresholds
  * Scheduled fleet operations
  * Pause / resume / cancel mid-flight
  * Per-operation progress aggregation
"""

from typing import Any, Dict, List, Optional, Tuple

# Operation types this planner can expand.  Mirrors the Pro+ enum so the
# free tier and licensed tier accept the same request shapes.
OPEN_SOURCE_OP_TYPES = (
    "run_script",
    "deploy_file",
    "service_control",
    "install_package",
    "remove_package",
    "reboot",
    "shutdown",
)


def expand_bulk_operation(
    operation_type: str,
    host_ids: List[str],
    parameters: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Expand a bulk-op request into per-host deploy plans.

    Args:
        operation_type: One of OPEN_SOURCE_OP_TYPES.
        host_ids: Explicit host UUIDs to run against.
        parameters: Operation-specific parameters; passed through verbatim
                    to the per-host plan as ``params``.

    Returns:
        A list of ``(host_id, plan_dict)`` tuples in the same order as
        ``host_ids``.  Empty list if ``host_ids`` is empty.

    Raises:
        ValueError: if ``operation_type`` is not in OPEN_SOURCE_OP_TYPES.
    """
    if operation_type not in OPEN_SOURCE_OP_TYPES:
        raise ValueError(
            f"Unsupported operation_type '{operation_type}'; "
            f"must be one of {OPEN_SOURCE_OP_TYPES}.  "
            f"Pro+ fleet_engine adds rolling deployments and apply_deployment_plan."
        )

    params = parameters or {}
    return [(hid, _build_plan(operation_type, params)) for hid in host_ids]


def _build_plan(op_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Map an operation_type + params dict into a deploy plan."""
    if op_type == "run_script":
        # Defer to script_plan_builder for the heavy lifting
        from backend.services.script_plan_builder import build_adhoc_script_plan

        return build_adhoc_script_plan(
            content=params.get("content", ""),
            shell=params.get("shell", "bash"),
            timeout_seconds=int(params.get("timeout_seconds", 300)),
            parameter_values=params.get("parameter_values"),
        )

    if op_type == "deploy_file":
        return {
            "files": [
                {
                    "path": params["path"],
                    "content": params["content"],
                    "mode": params.get("mode", 0o644),
                }
            ],
            "commands": [],
        }

    if op_type == "service_control":
        action = params.get("action", "restart")
        services = params.get("services") or [params.get("service")]
        return {
            "files": [],
            "commands": [],
            "service_actions": [
                {"service": svc, "action": action} for svc in services if svc
            ],
        }

    if op_type == "install_package":
        return {
            "packages": params.get("packages") or [params.get("package")],
            "files": [],
            "commands": [],
        }

    if op_type == "remove_package":
        return {
            "packages_to_remove": params.get("packages") or [params.get("package")],
            "files": [],
            "commands": [],
        }

    if op_type == "reboot":
        return {
            "files": [],
            "commands": [
                {
                    "argv": ["reboot"],
                    "timeout": 30,
                    "ignore_errors": True,
                    "description": "reboot host",
                }
            ],
        }

    if op_type == "shutdown":
        return {
            "files": [],
            "commands": [
                {
                    "argv": ["shutdown", "-h", "now"],
                    "timeout": 30,
                    "ignore_errors": True,
                    "description": "shut down host",
                }
            ],
        }

    # Defensive: shouldn't reach here because op_type was validated above.
    return {"files": [], "commands": []}
