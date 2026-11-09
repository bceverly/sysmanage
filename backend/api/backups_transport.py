# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""How hosts reach a target's storage (ROADMAP 25.5).

``PUT /backups/targets/{id}/transport`` -- NFS (every target until now), or
restate-proxy on the storage host at an address and port hosts can reach,
optionally trusted through a site CA (kept when none is sent, unless
``remove_proxy_ca``) or a pinned key.  The repositories stay
where they are, so a target switches either way.  Manage Backups; audited;
every host's and the storage host's jobs are re-sent.  Community: the proxy
is restate's own, free to run.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _require, _target_or_404
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_tick
from backend.services import backup_views as views
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

_REFUSALS = {
    "Unknown transport": lambda: _("Unknown transport"),
    "The proxy address is not a host name or IP address": lambda: _(
        "The proxy address is not a host name or IP address"
    ),
    "The proxy port must be between 1 and 65535": lambda: _(
        "The proxy port must be between 1 and 65535"
    ),
    "The pinned key must be a SHA-256 in hex (64 characters)": lambda: _(
        "The pinned key must be a SHA-256 in hex (64 characters)"
    ),
    "The proxy's CA must be a PEM certificate": lambda: _(
        "The proxy's CA must be a PEM certificate"
    ),
}


class TransportBody(BaseModel):
    transport: str = Field(min_length=1, max_length=16)
    proxy_host: Optional[str] = Field(default=None, max_length=255)
    proxy_port: Optional[int] = None
    proxy_pin_sha256: Optional[str] = Field(default=None, max_length=64)
    proxy_ca_pem: Optional[str] = Field(default=None, max_length=proxy.MAX_CA_BYTES)
    # No CA sent keeps the saved one; this removes it.
    remove_proxy_ca: bool = False


@router.put("/backups/targets/{target_id}/transport")
async def set_transport(
    target_id: str,
    body: TransportBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = _target_or_404(db, target_id)
    try:
        settings = proxy.check_settings(
            body.transport, body.proxy_host, body.proxy_port,
            body.proxy_pin_sha256, body.proxy_ca_pem,
        )  # fmt: skip
    except proxy.ProxySettingsRefused as refused:
        message = _REFUSALS.get(str(refused), lambda: str(refused))()
        raise HTTPException(status_code=422, detail=message) from refused
    keep_ca = (
        settings["transport"] == proxy.PROXY
        and settings["proxy_ca_pem"] is None
        and not body.remove_proxy_ca
    )
    if keep_ca:
        settings["proxy_ca_pem"] = target.proxy_ca_pem
    for column, value in settings.items():
        setattr(target, column, value)
    target.updated_at = jobs.now()
    # Hosts learn where to read; the storage host writes or removes grants.
    for policy in (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    ):
        policy.config_version += 1
        policy.updated_at = jobs.now()
    proxy.sync_clients(db, target)  # the clients the grants are now built for
    _audit(
        db, current_user, EntityType.SETTING, target.id, target.name,
        "Backup target transport changed",
        {k: v for k, v in settings.items() if k != "proxy_ca_pem"}
        | {"proxy_ca": bool(settings["proxy_ca_pem"])},
    )  # fmt: skip
    backup_tick.configure_now(db)
    db.commit()
    return views.target_dict(target, db)
