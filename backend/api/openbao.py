"""
This module contains the API implementation for OpenBAO (Vault) management in the system.
"""

import json
import logging
import os
import platform
import subprocess  # nosec B404 - Required for OpenBAO process management
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.auth_bearer import JWTBearer
from backend.config import config
from backend.i18n import _

router = APIRouter()
logger = logging.getLogger(__name__)


def get_openbao_status() -> Dict[str, Any]:
    """
    Get the current status of the OpenBAO server.
    Returns a dictionary with status information.
    """
    project_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    pid_file = os.path.join(project_dir, ".openbao.pid")
    log_file = os.path.join(project_dir, "logs", "openbao.log")

    # Check if PID file exists
    if not os.path.exists(pid_file):
        return {
            "running": False,
            "status": "stopped",
            "message": _("openbao.not_running", "OpenBAO is not running"),
            "pid": None,
            "server_url": None,
            "health": None,
            "sealed": None,
        }

    # Read PID
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (ValueError, IOError):
        return {
            "running": False,
            "status": "error",
            "message": _("openbao.invalid_pid", "Invalid PID file"),
            "pid": None,
            "server_url": None,
            "health": None,
            "sealed": None,
        }

    # Check if process is running
    process_running = False
    try:
        if platform.system() == "Windows":
            # Windows-specific process check using tasklist with full path
            result = subprocess.run(  # nosec B607 B603
                [
                    "C:\\Windows\\System32\\tasklist.exe",
                    "/FI",
                    f"PID eq {pid}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            # If process exists, tasklist will include it in output (check for quoted PID)
            process_running = f'"{pid}"' in result.stdout or str(pid) in result.stdout
        else:
            # Unix-specific process check
            os.kill(pid, 0)  # This doesn't kill, just checks if process exists
            process_running = True
    except (OSError, subprocess.SubprocessError):
        process_running = False

    if not process_running:
        # Process not found, clean up stale PID file
        try:
            os.remove(pid_file)
        except OSError:
            pass
        return {
            "running": False,
            "status": "stopped",
            "message": _("openbao.process_not_found", "OpenBAO process not found"),
            "pid": None,
            "server_url": None,
            "health": None,
            "sealed": None,
        }

    # Process is running, get additional info
    vault_config = config.get_vault_config()
    server_url = vault_config.get("url", "http://127.0.0.1:8200")

    # Try to get health status and seal status from OpenBAO API
    health_info = None
    seal_status = None
    try:
        # Find OpenBAO binary
        bao_cmd = find_bao_binary()
        if bao_cmd:
            env = os.environ.copy()
            env["BAO_ADDR"] = server_url
            env["BAO_TOKEN"] = vault_config.get("token", "")

            # bao_cmd is validated by find_bao_binary, status is a safe fixed argument
            result = subprocess.run(  # nosec B603
                [bao_cmd, "status"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
                check=False,
            )

            if result.returncode == 0:
                # Parse status output for key information
                status_lines = result.stdout.strip().split("\n")
                health_info = {}
                for line in status_lines:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key_clean = key.strip()
                        value_clean = value.strip()
                        health_info[key_clean] = value_clean

                        # Extract seal status
                        if key_clean.lower() == "sealed":
                            seal_status = value_clean.lower() in ["true", "yes", "1"]
            else:
                health_info = {
                    "error": result.stderr.strip() if result.stderr else "Unknown error"
                }
                # If we can't get status due to sealed vault, try to determine seal status
                if "sealed" in result.stderr.lower():
                    seal_status = True
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        health_info = {"error": "Unable to connect to OpenBAO server"}

    # Get recent log entries
    recent_logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                recent_logs = [line.strip() for line in lines[-5:] if line.strip()]
        except IOError:
            recent_logs = ["Unable to read log file"]

    return {
        "running": process_running,
        "status": "running",
        "message": _("openbao.running", "OpenBAO is running"),
        "pid": pid,
        "server_url": server_url,
        "health": health_info,
        "recent_logs": recent_logs,
        "sealed": seal_status,
    }


def find_bao_binary() -> Optional[str]:
    """Find the OpenBAO binary in the system."""
    # Check common locations
    locations = [
        "bao",  # In PATH
        os.path.expanduser("~/.local/bin/bao"),
        "/usr/local/bin/bao",
        "/usr/bin/bao",
    ]

    for location in locations:
        try:
            if location == "bao":
                # Check if it's in PATH
                # Use shutil.which for safe path lookup instead of subprocess
                import shutil

                which_result = shutil.which("bao")
                if which_result:
                    return "bao"
            else:
                # Check if file exists and is executable
                if os.path.isfile(location) and os.access(location, os.X_OK):
                    return location
        except (OSError, FileNotFoundError, PermissionError):
            continue

    return None


def start_openbao() -> Dict[str, Any]:
    """
    Start the OpenBAO development server.
    """
    # Check if already running
    status = get_openbao_status()
    if status["running"]:
        return {
            "success": True,
            "message": _("openbao.already_running", "OpenBAO is already running"),
            "status": status,
        }

    # Find project directory and script
    project_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    # Choose script based on operating system
    if platform.system() == "Windows":
        # Use PowerShell script with proper background execution
        start_script = os.path.join(project_dir, "scripts", "start-openbao.ps1")
        start_script_fallback = os.path.join(
            project_dir, "scripts", "start-openbao.cmd"
        )
    else:
        start_script = os.path.join(project_dir, "scripts", "start-openbao.sh")
        start_script_fallback = None

    if not os.path.exists(start_script):
        if start_script_fallback and os.path.exists(start_script_fallback):
            start_script = start_script_fallback
        else:
            raise HTTPException(
                status_code=500,
                detail=_("openbao.script_not_found", "OpenBAO start script not found"),
            )

    try:
        # Run the start script
        # start_script path is validated above, located in trusted project directory
        if platform.system() == "Windows":
            if start_script.endswith(".ps1"):
                # Use scheduled task approach to completely isolate from Python process
                try:
                    import time
                    import uuid

                    # Generate unique task name
                    task_name = f"SysManage_OpenBao_Start_{uuid.uuid4().hex[:8]}"

                    # Create one-time scheduled task to run the script
                    schtasks_cmd = [
                        "C:\\Windows\\System32\\schtasks.exe",
                        "/create",
                        "/tn",
                        task_name,
                        "/tr",
                        f'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "{start_script}"',
                        "/sc",
                        "once",
                        "/st",
                        "00:00",
                        "/sd",
                        "01/01/2025",
                        "/f",  # Force overwrite if exists
                    ]

                    # Create the task
                    create_result = subprocess.run(  # nosec B607 B603
                        schtasks_cmd, capture_output=True, text=True, check=False
                    )

                    if create_result.returncode == 0:
                        # Run the task immediately
                        run_result = subprocess.run(  # nosec B607 B603
                            [
                                "C:\\Windows\\System32\\schtasks.exe",
                                "/run",
                                "/tn",
                                task_name,
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                        )

                        # Wait a moment for it to start
                        time.sleep(3)

                        # Clean up the task
                        subprocess.run(  # nosec B607 B603
                            [
                                "C:\\Windows\\System32\\schtasks.exe",
                                "/delete",
                                "/tn",
                                task_name,
                                "/f",
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                        )

                        # Create success result
                        class Result:
                            def __init__(self):
                                self.returncode = 0
                                self.stdout = "OpenBao started via scheduled task"
                                self.stderr = ""

                        result = Result()
                    else:
                        raise Exception(
                            f"Failed to create scheduled task: {create_result.stderr}"
                        )

                except Exception as e:

                    class Result:
                        def __init__(self, error):
                            self.returncode = 1
                            self.stdout = ""
                            self.stderr = str(error)

                    result = Result(e)
            else:
                # CMD script fallback - avoid shell=True for security
                result = subprocess.run(  # nosec B607 B603
                    ["C:\\Windows\\System32\\cmd.exe", "/c", start_script],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=project_dir,
                    check=False,
                )
        else:
            # Unix shell script
            result = subprocess.run(  # nosec B603
                [start_script],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_dir,
                check=False,
            )

        if result.returncode == 0:
            # Wait a moment for startup and get status
            import time

            time.sleep(2)
            new_status = get_openbao_status()

            return {
                "success": True,
                "message": _("openbao.started", "OpenBAO started successfully"),
                "status": new_status,
                "output": result.stdout,
            }
        else:
            return {
                "success": False,
                "message": _("openbao.start_failed", "Failed to start OpenBAO"),
                "error": result.stderr or result.stdout,
                "status": get_openbao_status(),
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": _("openbao.start_timeout", "OpenBAO start timed out"),
            "status": get_openbao_status(),
        }
    except Exception as e:
        return {
            "success": False,
            "message": _(
                "openbao.start_error", "Error starting OpenBAO: {error}"
            ).format(error=str(e)),
            "status": get_openbao_status(),
        }


def stop_openbao() -> Dict[str, Any]:
    """
    Stop the OpenBAO development server.
    """
    # Check if running
    status = get_openbao_status()
    if not status["running"]:
        return {
            "success": True,
            "message": _("openbao.not_running", "OpenBAO is not running"),
            "status": status,
        }

    # Find project directory and script
    project_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    # Choose script based on operating system
    if platform.system() == "Windows":
        # Use PowerShell script with proper background execution
        stop_script = os.path.join(project_dir, "scripts", "stop-openbao.ps1")
        stop_script_fallback = os.path.join(project_dir, "scripts", "stop-openbao.cmd")
    else:
        stop_script = os.path.join(project_dir, "scripts", "stop-openbao.sh")
        stop_script_fallback = None

    if not os.path.exists(stop_script):
        if stop_script_fallback and os.path.exists(stop_script_fallback):
            stop_script = stop_script_fallback
        else:
            raise HTTPException(
                status_code=500,
                detail=_("openbao.script_not_found", "OpenBAO stop script not found"),
            )

    try:
        # Run the stop script
        # stop_script path is validated above, located in trusted project directory
        if platform.system() == "Windows":
            if stop_script.endswith(".ps1"):
                # PowerShell script with full path
                result = subprocess.run(  # nosec B607 B603
                    [
                        "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                        "-WindowStyle",
                        "Hidden",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        stop_script,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=project_dir,
                    check=False,
                )
            else:
                # CMD script fallback - avoid shell=True for security
                result = subprocess.run(  # nosec B607 B603
                    ["C:\\Windows\\System32\\cmd.exe", "/c", stop_script],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=project_dir,
                    check=False,
                )
        else:
            # Unix shell script
            result = subprocess.run(  # nosec B603
                [stop_script],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=project_dir,
                check=False,
            )

        if result.returncode == 0:
            # Wait a moment for shutdown and get status
            import time

            time.sleep(1)
            new_status = get_openbao_status()

            return {
                "success": True,
                "message": _("openbao.stopped", "OpenBAO stopped successfully"),
                "status": new_status,
                "output": result.stdout,
            }
        else:
            return {
                "success": False,
                "message": _("openbao.stop_failed", "Failed to stop OpenBAO"),
                "error": result.stderr or result.stdout,
                "status": get_openbao_status(),
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": _("openbao.stop_timeout", "OpenBAO stop timed out"),
            "status": get_openbao_status(),
        }
    except Exception as e:
        logger.error("Exception occurred while stopping OpenBAO:\n%s", e, exc_info=True)
        return {
            "success": False,
            "message": _("openbao.generic_error", "An error occurred while stopping OpenBAO"),
            "status": get_openbao_status(),
        }


def seal_openbao() -> Dict[str, Any]:
    """
    Seal the OpenBAO vault.
    """
    # Check if running
    status = get_openbao_status()
    if not status["running"]:
        return {
            "success": False,
            "message": _("openbao.not_running", "OpenBAO is not running"),
            "status": status,
        }

    # Check if already sealed
    if status.get("sealed") is True:
        return {
            "success": True,
            "message": _("openbao.already_sealed", "OpenBAO is already sealed"),
            "status": status,
        }

    try:
        # Find OpenBAO binary
        bao_cmd = find_bao_binary()
        if not bao_cmd:
            return {
                "success": False,
                "message": _("openbao.binary_not_found", "OpenBAO binary not found"),
                "status": status,
            }

        vault_config = config.get_vault_config()
        env = os.environ.copy()
        env["BAO_ADDR"] = vault_config.get("url", "http://127.0.0.1:8200")
        env["BAO_TOKEN"] = vault_config.get("token", "")

        # bao_cmd is validated by find_bao_binary, operator seal is a safe fixed argument
        result = subprocess.run(  # nosec B603
            [bao_cmd, "operator", "seal"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            check=False,
        )

        if result.returncode == 0:
            # Wait a moment and get updated status
            import time

            time.sleep(1)
            new_status = get_openbao_status()

            return {
                "success": True,
                "message": _("openbao.sealed", "OpenBAO sealed successfully"),
                "status": new_status,
                "output": result.stdout,
            }
        else:
            return {
                "success": False,
                "message": _("openbao.seal_failed", "Failed to seal OpenBAO"),
                # "error": result.stderr or result.stdout,  # Commented out to avoid exposing details
                "status": get_openbao_status(),
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": _("openbao.seal_timeout", "OpenBAO seal operation timed out"),
            "status": get_openbao_status(),
        }
    except Exception as e:
        logger.exception("Exception occurred while sealing OpenBAO")  # Log full traceback for server-side debugging
        return {
            "success": False,
            "message": _("openbao.seal_error", "Error sealing OpenBAO"),
            "status": get_openbao_status(),
        }



def unseal_openbao() -> Dict[str, Any]:
    """
    Unseal the OpenBAO vault using the configured dev token.
    Note: This is for development mode only.
    """
    # Check if running
    status = get_openbao_status()
    if not status["running"]:
        return {
            "success": False,
            "message": _("openbao.not_running", "OpenBAO is not running"),
            "status": status,
        }

    # Check if already unsealed
    if status.get("sealed") is False:
        return {
            "success": True,
            "message": _("openbao.already_unsealed", "OpenBAO is already unsealed"),
            "status": status,
        }

    vault_config = config.get_vault_config()

    # Check if we're in dev mode
    if not vault_config.get("dev_mode", False):
        return {
            "success": False,
            "message": _(
                "openbao.unseal_prod_mode",
                "Automatic unseal is only supported in development mode",
            ),
            "status": status,
        }

    try:
        # Find OpenBAO binary
        bao_cmd = find_bao_binary()
        if not bao_cmd:
            return {
                "success": False,
                "message": _("openbao.binary_not_found", "OpenBAO binary not found"),
                "status": status,
            }

        env = os.environ.copy()
        env["BAO_ADDR"] = vault_config.get("url", "http://127.0.0.1:8200")
        env["BAO_TOKEN"] = vault_config.get("token", "")

        # In dev mode, try to use the dev token to unseal
        # This works because dev mode typically uses a fixed unseal key
        result = subprocess.run(  # nosec B603
            [bao_cmd, "operator", "unseal", "-address", env["BAO_ADDR"]],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            check=False,
            input="dev-only-token-change-me\n",  # Dev mode unseal key
        )

        if result.returncode == 0:
            # Wait a moment and get updated status
            import time

            time.sleep(1)
            new_status = get_openbao_status()

            return {
                "success": True,
                "message": _("openbao.unsealed", "OpenBAO unsealed successfully"),
                "status": new_status,
                "output": result.stdout,
            }
        else:
            return {
                "success": False,
                "message": _("openbao.unseal_failed", "Failed to unseal OpenBAO"),
                "error": result.stderr or result.stdout,
                "status": get_openbao_status(),
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": _(
                "openbao.unseal_timeout", "OpenBAO unseal operation timed out"
            ),
            "status": get_openbao_status(),
        }
    except Exception as e:
        logger.exception("Exception occurred while unsealing OpenBAO")
        return {
            "success": False,
            "message": _("openbao.unseal_error", "Error unsealing OpenBAO"),
            "status": get_openbao_status(),
        }


@router.get("/openbao/status", dependencies=[Depends(JWTBearer())])
async def get_status():
    """
    Get the current status of the OpenBAO server.
    """
    return get_openbao_status()


@router.post("/openbao/start", dependencies=[Depends(JWTBearer())])
async def start_server():
    """
    Start the OpenBAO development server.
    """
    try:
        result = start_openbao()
        # Sanitize potentially sensitive information from response
        sanitized_result = {"success": result.get("success", False)}
        if not sanitized_result["success"]:
            sanitized_result["error"] = _(
                "openbao.start_failed", "Failed to start OpenBAO"
            )
        return sanitized_result
    except HTTPException:
        raise
    except Exception:  # pylint: disable=broad-except
        # Don't log exception details to avoid information disclosure
        raise HTTPException(  # pylint: disable=raise-missing-from
            status_code=500,
            detail=_(
                "openbao.generic_error", "An error occurred while starting OpenBAO"
            ),
        )


@router.post("/openbao/stop", dependencies=[Depends(JWTBearer())])
async def stop_server():
    """
    Stop the OpenBAO development server.
    """
    try:
        result = stop_openbao()
        # Sanitize potentially sensitive information from response
        sanitized_result = {"success": result.get("success", False)}
        if not sanitized_result["success"]:
            sanitized_result["error"] = _(
                "openbao.stop_failed", "Failed to stop OpenBAO"
            )
        return sanitized_result
    except HTTPException:
        raise
    except Exception:  # pylint: disable=broad-except
        # Don't log exception details to avoid information disclosure
        raise HTTPException(  # pylint: disable=raise-missing-from
            status_code=500,
            detail=_(
                "openbao.generic_error", "An error occurred while stopping OpenBAO"
            ),
        )


@router.get("/openbao/config", dependencies=[Depends(JWTBearer())])
async def get_config():
    """
    Get the current OpenBAO configuration from sysmanage settings.
    """
    vault_config = config.get_vault_config()

    # Remove sensitive information
    safe_config = {
        "enabled": vault_config.get("enabled", False),
        "url": vault_config.get("url", "http://localhost:8200"),
        "mount_path": vault_config.get("mount_path", "secret"),
        "timeout": vault_config.get("timeout", 30),
        "verify_ssl": vault_config.get("verify_ssl", True),
        "dev_mode": vault_config.get("dev_mode", False),
        "has_token": bool(vault_config.get("token", "").strip()),
    }

    return safe_config


@router.post("/openbao/seal", dependencies=[Depends(JWTBearer())])
async def seal_vault():
    """
    Seal the OpenBAO vault.
    """
    try:
        result = seal_openbao()
        # Sanitize potentially sensitive information from response
        sanitized_result = {"success": result.get("success", False)}
        if not sanitized_result["success"]:
            sanitized_result["error"] = _(
                "openbao.seal_failed", "Failed to seal OpenBAO"
            )
        return sanitized_result
    except HTTPException:
        raise
    except Exception:  # pylint: disable=broad-except
        # Don't log exception details to avoid information disclosure
        raise HTTPException(  # pylint: disable=raise-missing-from
            status_code=500,
            detail=_(
                "openbao.generic_error", "An error occurred while sealing OpenBAO"
            ),
        )


@router.post("/openbao/unseal", dependencies=[Depends(JWTBearer())])
async def unseal_vault():
    """
    Unseal the OpenBAO vault.
    """
    try:
        result = unseal_openbao()
        # Sanitize potentially sensitive information from response
        sanitized_result = {"success": result.get("success", False)}
        if not sanitized_result["success"]:
            sanitized_result["error"] = _(
                "openbao.unseal_failed", "Failed to unseal OpenBAO"
            )
        return sanitized_result
    except HTTPException:
        raise
    except Exception:  # pylint: disable=broad-except
        # Don't log exception details to avoid information disclosure
        raise HTTPException(  # pylint: disable=raise-missing-from
            status_code=500,
            detail=_(
                "openbao.generic_error", "An error occurred while unsealing OpenBAO"
            ),
        )
