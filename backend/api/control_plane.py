"""
Control-plane API — OSS stub (Pro+ relocation, Phase 3 / moat slice 8).

The entire multi-tenancy control-plane API — tenant / user / grant /
email-domain / placement CRUD, provisioning, enrollment tokens, and tenant
deletion — moved into the licensed ``multitenancy_engine``.  The OSS build
ships only this inert stub.

``mount_multitenancy_routes`` (see ``backend/api/proplus_routes.py``) mounts the
engine's real router when the licensed engine is loaded; this stub is mounted
only when multi-tenancy is *configured* but the engine is **not** present, in
which case every control-plane route answers ``501 Not Implemented`` so an
unlicensed fork cannot operate a SaaS control plane.  That absence of logic in
the public source is the technical moat.

The router keeps the same effective ``/api/v1/control-plane`` surface (mounted by
``proplus_routes``; ``/api/control-plane`` stays as a deprecated alias) and
bearer-token gate so an unauthenticated probe is still rejected (401/403) before
it learns the plane is unlicensed.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.auth_bearer import JWTBearer

logger = logging.getLogger(__name__)

# Highly privileged surface — gate the whole (stub) router on a valid token, so
# the unlicensed 501 is only revealed to authenticated callers.
# Self-prefix only "/control-plane"; proplus_routes mounts this at "/api/v1"
# (canonical) + "/api" (deprecated alias).  See Phase 13.2.1.
router = APIRouter(
    prefix="/control-plane",
    tags=["control-plane"],
    dependencies=[Depends(JWTBearer())],
)

_UNLICENSED_DETAIL = (
    "The multi-tenancy control plane requires the licensed multitenancy_engine "
    "(Pro+ MULTITENANT_SAAS), which is not loaded on this server."
)


@router.api_route(
    "/{_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    include_in_schema=False,
)
def _unlicensed(_path: str):
    """Catch-all: the control plane is configured but the engine is absent."""
    raise HTTPException(status_code=501, detail=_UNLICENSED_DETAIL)
