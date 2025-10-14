"""
Secrets API module.

This module provides API endpoints for managing secrets including:
- Secret CRUD operations (create, read, update, delete)
- Secret type definitions
- SSH key deployment
- SSL certificate deployment
"""

from fastapi import APIRouter

from . import crud, deployment, types

# Create main router for secrets
router = APIRouter()

# Include all sub-routers
# IMPORTANT: Include types.router BEFORE crud.router to avoid route conflicts
# The /secrets/types route must be registered before /secrets/{secret_id}
router.include_router(types.router, tags=["secrets"])
router.include_router(crud.router, tags=["secrets"])
router.include_router(deployment.router, tags=["secrets"])

__all__ = ["router"]
