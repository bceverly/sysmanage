"""
Child host management API endpoints.
Allows managing virtual machines, containers, and WSL instances on remote hosts.

This module aggregates all child host related endpoints from:
- child_host_crud: CRUD operations for child hosts
- child_host_control: Start/stop/restart operations
- child_host_virtualization: Virtualization support and WSL enablement
"""

from fastapi import APIRouter

from backend.api.child_host_control import router as control_router
from backend.api.child_host_crud import router as crud_router
from backend.api.child_host_virtualization import router as virtualization_router

# Re-export models for backwards compatibility
from backend.api.child_host_models import (  # noqa: F401
    ChildHostResponse,
    CreateChildHostRequest,
    CreateWslChildHostRequest,
    DistributionResponse,
    EnableWslRequest,
    VirtualizationSupportResponse,
)

router = APIRouter()

# Include all sub-routers
router.include_router(crud_router)
router.include_router(control_router)
router.include_router(virtualization_router)
