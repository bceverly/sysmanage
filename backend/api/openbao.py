"""
This module contains the API implementation for OpenBAO (Vault) management in the system.
"""

import subprocess
import os
import json
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from backend.auth.auth_bearer import JWTBearer
from backend.config import config
from backend.i18n import _

router = APIRouter()


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
        }

    # Check if process is running
    try:
        os.kill(pid, 0)  # This doesn't kill, just checks if process exists
        process_running = True
    except OSError:
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
        }

    # Process is running, get additional info
    vault_config = config.get_vault_config()
    server_url = vault_config.get("url", "http://127.0.0.1:8200")

    # Try to get health status from OpenBAO API
    health_info = None
    try:
        # Find OpenBAO binary
        bao_cmd = find_bao_binary()
        if bao_cmd:
            env = os.environ.copy()
            env["BAO_ADDR"] = server_url
            env["BAO_TOKEN"] = vault_config.get("token", "")

            result = subprocess.run(
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
                        health_info[key.strip()] = value.strip()
            else:
                health_info = {
                    "error": result.stderr.strip() if result.stderr else "Unknown error"
                }
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
                result = subprocess.run(
                    ["which", "bao"], capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    return "bao"
            else:
                # Check if file exists and is executable
                if os.path.isfile(location) and os.access(location, os.X_OK):
                    return location
        except:
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
    start_script = os.path.join(project_dir, "scripts", "start-openbao.sh")

    if not os.path.exists(start_script):
        raise HTTPException(
            status_code=500,
            detail=_("openbao.script_not_found", "OpenBAO start script not found"),
        )

    try:
        # Run the start script
        result = subprocess.run(
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
    stop_script = os.path.join(project_dir, "scripts", "stop-openbao.sh")

    if not os.path.exists(stop_script):
        raise HTTPException(
            status_code=500,
            detail=_("openbao.script_not_found", "OpenBAO stop script not found"),
        )

    try:
        # Run the stop script
        result = subprocess.run(
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
        return {
            "success": False,
            "message": _(
                "openbao.stop_error", "Error stopping OpenBAO: {error}"
            ).format(error=str(e)),
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
        return start_openbao()
    except HTTPException:
        raise
    except Exception as e:  # pylint: disable=broad-except
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
        return stop_openbao()
    except HTTPException:
        raise
    except Exception as e:  # pylint: disable=broad-except
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
