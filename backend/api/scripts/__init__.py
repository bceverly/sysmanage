# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Script management API module.

This module provides API routes for:
- Saved script CRUD operations
- Script execution and monitoring
- Script execution log management
"""

from fastapi import APIRouter

from .models import (
    SavedScriptCreate,
    SavedScriptResponse,
    SavedScriptUpdate,
    ScriptExecutionLogResponse,
    ScriptExecutionRequest,
    ScriptExecutionResponse,
    ScriptExecutionsResponse,
)
from .routes_executions import router as executions_router
from .routes_saved_scripts import router as saved_scripts_router

# Create main router and include sub-routers
router = APIRouter()
router.include_router(saved_scripts_router)
router.include_router(executions_router)

# Export public API
__all__ = [
    "router",
    "SavedScriptCreate",
    "SavedScriptUpdate",
    "SavedScriptResponse",
    "ScriptExecutionRequest",
    "ScriptExecutionResponse",
    "ScriptExecutionLogResponse",
    "ScriptExecutionsResponse",
]
