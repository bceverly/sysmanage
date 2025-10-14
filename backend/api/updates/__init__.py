"""Package update management API routes.

This module aggregates all update-related routers into a single router
that can be imported and included in the main application.
"""

from fastapi import APIRouter

from . import execution_routes, os_upgrade_routes, query_routes, report_routes

# Create main router that combines all sub-routers
router = APIRouter()

# Include all sub-routers
router.include_router(report_routes.router, tags=["updates"])
router.include_router(query_routes.router, tags=["updates"])
router.include_router(execution_routes.router, tags=["updates"])
router.include_router(os_upgrade_routes.router, tags=["updates"])

__all__ = ["router"]
