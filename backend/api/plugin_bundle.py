"""
Plugin bundle serving endpoint.

Serves Pro+ frontend plugin JavaScript bundles to the browser.
Plugin bundles are IIFE scripts that register themselves with
the host application's plugin system.
"""

import glob
import os
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.auth.auth_bearer import get_current_user
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.plugin_bundle")

router = APIRouter()

# Default directory where plugin bundles are stored
DEFAULT_MODULES_PATH = "/var/lib/sysmanage/modules"


class PluginBundleListResponse(BaseModel):
    """Response listing available plugin bundle URLs."""

    bundles: List[str]


def _get_modules_path() -> str:
    """Get the configured modules path."""
    from backend.config.config import get_config

    config = get_config()
    license_config = config.get("license", {})
    return license_config.get("modules_path", DEFAULT_MODULES_PATH)


@router.get(
    "/plugins/bundles",
    response_model=PluginBundleListResponse,
)
async def list_plugin_bundles(
    _current_user: dict = Depends(get_current_user),
):
    """
    List available plugin bundles.

    Returns URLs for each available plugin JS bundle that the
    frontend should load. Dynamically discovers all *-plugin.iife.js
    files in the modules directory.
    """
    modules_path = _get_modules_path()

    bundles: List[str] = []
    pattern = os.path.join(modules_path, "*-plugin.iife.js")
    for bundle_path in sorted(glob.glob(pattern)):
        filename = os.path.basename(bundle_path)
        bundles.append(f"/api/plugins/bundle/{filename}")

    return PluginBundleListResponse(bundles=bundles)


@router.get("/plugins/bundle/{filename}")
async def get_plugin_bundle(
    filename: str,
    _current_user: dict = Depends(get_current_user),
):
    """
    Serve a specific plugin bundle file.

    Only serves files with a .js extension from the modules directory.
    """
    # Security: only allow .js files, no path traversal characters
    if not filename.endswith(".js") or "/" in filename or "\\" in filename:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid bundle filename"},
        )

    # Additional check: reject any path traversal attempts
    if ".." in filename:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid bundle filename"},
        )

    modules_path = _get_modules_path()

    # Resolve the real paths to prevent path traversal attacks
    # This handles symlinks and normalizes the path
    real_modules_path = os.path.realpath(modules_path)
    bundle_path = os.path.realpath(os.path.join(modules_path, filename))

    # Security: ensure the resolved path is within the modules directory
    if not bundle_path.startswith(real_modules_path + os.sep):
        logger.warning(
            "Path traversal attempt detected: %s resolved to %s",
            filename,
            bundle_path,
        )
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid bundle filename"},
        )

    if not os.path.isfile(bundle_path):
        return JSONResponse(
            status_code=404,
            content={"error": "Plugin bundle not found"},
        )

    return FileResponse(
        bundle_path,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )
