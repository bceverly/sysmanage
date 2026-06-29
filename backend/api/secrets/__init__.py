"""
Secrets API module.

This module provides API endpoints for managing secrets including:
- Secret CRUD operations (create, read, update, delete)
- Secret type definitions
- SSH key deployment
- SSL certificate deployment

Phase 13.2.1: the collection routes use a bare ``""`` path (the feature root),
which FastAPI only permits when the router is mounted under a non-empty prefix.
So instead of pre-aggregating the sub-routers into a single prefix-less router
here, they are exposed individually and registered (in order) by
``route_registration`` under the feature prefix (``/api/v1/stored-secrets`` +
the deprecated ``/api/secrets`` alias).

ORDER MATTERS: ``types_router`` must be registered BEFORE ``crud_router`` so the
``/types`` route is matched before ``/{secret_id}``.
"""

from . import crud, deployment, types

# Ordered tuple — route_registration mounts these under the feature prefix(es).
ordered_routers = (types.router, crud.router, deployment.router)

__all__ = ["ordered_routers"]
