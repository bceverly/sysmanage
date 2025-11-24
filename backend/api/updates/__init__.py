"""Package update management API routes.

This module aggregates all update-related routers into a single router
that can be imported and included in the main application.
"""

from fastapi import APIRouter

from . import execution_routes, os_upgrade_routes, query_routes, report_routes

# Create main router that combines all sub-routers
router = APIRouter()

# Include all sub-routers
# IMPORTANT: Order matters! More specific routes must come before generic catch-all routes
# os_upgrade_routes has specific routes like /os-upgrades that must be registered
# before query_routes which has a catch-all /{host_id} route
router.include_router(report_routes.router, tags=["updates"])
router.include_router(os_upgrade_routes.router, tags=["updates"])
router.include_router(execution_routes.router, tags=["updates"])
router.include_router(query_routes.router, tags=["updates"])

__all__ = ["router"]
