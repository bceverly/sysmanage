"""
Free-tier (open-source) script plan builder.

Generates declarative script-execution plans for ad-hoc, single-shot
script runs against ONE host.  The plans use the same shape that the
Pro+ automation_engine.build_script_command_plan emits, so the agent
receives one consistent message type via the generic
``apply_deployment_plan`` handler.

Plan shape:

    {
        "files":    [{"path": "/tmp/.../script.sh", "content": "...", "mode": 0o700}],
        "commands": [
            {"argv": [interpreter, script_path], "timeout": N, "ignore_errors": False, ...},
            {"argv": ["rm", "-f", script_path], "timeout": 10, "ignore_errors": True, ...},
        ],
    }

Pro+ licensees get the richer engine in
sysmanage-professional-plus/module-source/automation_engine which adds:
  * Saved-script library with version history
  * Multi-host execution
  * Scheduled execution
  * Approval workflows for privileged scripts
  * Per-execution stdout/stderr capture and rollup status
  * Typed parameter declarations + validated value substitution
"""

from typing import Any, Dict, Optional
from uuid import uuid4

SUPPORTED_SHELLS = ("bash", "zsh", "sh", "ksh", "powershell", "cmd")


def build_adhoc_script_plan(
    content: str,
    shell: str = "bash",
    timeout_seconds: int = 300,
    parameter_values: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a one-shot script execution plan.

    Args:
        content: The script body.  Supports ``${name}`` placeholders that
                 are substituted from ``parameter_values`` before dispatch.
        shell: One of bash, zsh, sh, ksh, powershell, cmd.
        timeout_seconds: How long the agent waits for the script to finish.
        parameter_values: Optional dict of ``{name: value}`` substitutions.
                          Unknown placeholders are left untouched.

    Returns:
        A deploy plan dict the agent's ``apply_deployment_plan`` handler
        understands directly.

    Raises:
        ValueError: if the shell is not supported.
    """
    if shell not in SUPPORTED_SHELLS:
        raise ValueError(
            f"Unsupported shell '{shell}'; must be one of {SUPPORTED_SHELLS}"
        )

    rendered = _render(content, parameter_values or {})

    if shell == "powershell":
        script_path = f"C:/Windows/Temp/sysmanage_script_{uuid4().hex}.ps1"
        argv = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path]
        cleanup = ["powershell", "-Command", f"Remove-Item -Force '{script_path}'"]
    elif shell == "cmd":
        script_path = f"C:/Windows/Temp/sysmanage_script_{uuid4().hex}.bat"
        argv = ["cmd.exe", "/c", script_path]
        cleanup = ["cmd.exe", "/c", "del", script_path]
    else:
        # POSIX shells.  /tmp is fine here despite Sonar S5443: the path uses
        # uuid4().hex (128 bits of cryptographic randomness, unpredictable to
        # any local attacker) and the agent's deploy_files handler writes the
        # file atomically (sibling-temp + rename) with mode 0o700 set before
        # the rename — a pre-existing symlink at this exact path is
        # essentially impossible AND would cause the rename to fail rather
        # than overwrite, so symlink attacks don't apply.
        script_path = f"/tmp/sysmanage_script_{uuid4().hex}.sh"  # NOSONAR S5443 - see comment above
        argv = [f"/bin/{shell}", script_path]
        cleanup = ["rm", "-f", script_path]

    return {
        "files": [
            {
                "path": script_path,
                "content": rendered,
                "mode": 0o700,
            }
        ],
        "commands": [
            {
                "argv": argv,
                "timeout": int(timeout_seconds),
                "ignore_errors": False,
                "description": f"run ad-hoc sysmanage script via {shell}",
            },
            {
                "argv": cleanup,
                "timeout": 10,
                "ignore_errors": True,
                "description": "remove temporary script file",
            },
        ],
    }


def _render(template: str, values: Dict[str, Any]) -> str:
    """Substitute ``${name}`` placeholders left-to-right."""
    rendered = template
    for name, value in values.items():
        rendered = rendered.replace("${" + name + "}", str(value))
    return rendered
