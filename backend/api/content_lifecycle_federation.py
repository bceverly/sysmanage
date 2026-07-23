# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content Lifecycle Management — federated site sync API (Phase 16, Slice 7b).

Coordinator-side management of which federation SITES subscribe to which
lifecycle ENVIRONMENTS.  When a content-view version is promoted into a
subscribed environment, the coordinator announces it to each site (a metadata
push), and the site's mirror host pulls the version's bytes over HTTP and serves
them locally.  This module owns the subscription CRUD; the announce-on-promote
hook and the site-side receive/pull live alongside the promotion + serving code.

Split out of ``backend.api.content_lifecycle`` (line-count cap); mounts its own
router and reuses that module's gate + lookup helpers.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.content_lifecycle import _check_clm_module, _get_env_or_404
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_shared_db, get_tenant_db

logger = logging.getLogger(__name__)

router = APIRouter()


class SubscriptionCreate(BaseModel):
    site_id: str


def _require_coordinator() -> None:
    """Subscriptions are a coordinator-side concept (it decides which sites get
    which env's content)."""
    from backend.services.server_config_service import (
        get_federation_role,
    )  # noqa: PLC0415

    if get_federation_role() != "coordinator":
        raise HTTPException(
            status_code=400,
            detail=_(
                "Environment subscriptions are managed on the federation coordinator"
            ),
        )


def _subscription_for(tenant_db: Session, env_id, site_id):
    return (
        tenant_db.query(models.EnvironmentSiteSubscription)
        .filter(models.EnvironmentSiteSubscription.environment_id == env_id)
        .filter(models.EnvironmentSiteSubscription.site_id == site_id)
        .first()
    )


@router.get(
    "/content-lifecycle/environments/{env_id}/subscriptions",
    dependencies=[Depends(JWTBearer())],
)
async def list_subscriptions(
    env_id: str,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
):
    """The federation sites subscribed to an environment (they receive CVVs
    promoted into it)."""
    _check_clm_module()
    _get_env_or_404(shared_db, env_id)
    rows = (
        tenant_db.query(models.EnvironmentSiteSubscription)
        .filter(models.EnvironmentSiteSubscription.environment_id == env_id)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post(
    "/content-lifecycle/environments/{env_id}/subscriptions",
    dependencies=[Depends(JWTBearer())],
)
async def create_subscription(
    env_id: str,
    body: SubscriptionCreate,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Subscribe a federation site to an environment (idempotent)."""
    _check_clm_module()
    _require_coordinator()
    env = _get_env_or_404(shared_db, env_id)
    existing = _subscription_for(tenant_db, env.id, body.site_id)
    if existing is not None:
        return existing.to_dict()
    sub = models.EnvironmentSiteSubscription(
        environment_id=env.id, site_id=body.site_id
    )
    tenant_db.add(sub)
    tenant_db.commit()
    tenant_db.refresh(sub)
    return sub.to_dict()


@router.delete(
    "/content-lifecycle/environments/{env_id}/subscriptions/{site_id}",
    dependencies=[Depends(JWTBearer())],
)
async def delete_subscription(
    env_id: str,
    site_id: str,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Unsubscribe a site from an environment."""
    _check_clm_module()
    _require_coordinator()
    _get_env_or_404(shared_db, env_id)
    sub = _subscription_for(tenant_db, env_id, site_id)
    if sub is not None:
        tenant_db.delete(sub)
        tenant_db.commit()
    return {"deleted": True, "environment_id": env_id, "site_id": site_id}
