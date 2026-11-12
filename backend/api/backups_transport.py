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

``PUT /backups/targets/{id}/proxy-bandwidth`` -- bandwidth by the hour of the
storage host's day for every client of the proxy (restate-proxy's own
``bandwidth`` lines).  Professional+: 402 without the backup engine, except
to clear the rules; a lapsed license keeps them but stops sending them, so
proxy backups carry on at full speed (``services/backup_proxy_limits``).
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _require, _target_or_404
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.migration_compat import missing_engine_detail
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_proxy_limits as limits
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


_BANDWIDTH_REFUSALS = {
    "Give at most 25 bandwidth rules": lambda: _("Give at most 25 bandwidth rules"),
    "A bandwidth rule is a rate (512KiB/s, 2MiB/s, 1GiB/s or unlimited), or hours "
    "and a rate (08-18 2MiB/s)": lambda: _(
        "A bandwidth rule is a rate (512KiB/s, 2MiB/s, 1GiB/s or unlimited), or "
        "hours and a rate (08-18 2MiB/s)"
    ),
    "A bandwidth rate must be at least 64KiB/s": lambda: _(
        "A bandwidth rate must be at least 64KiB/s"
    ),
    "Give one rate for every other hour, not two": lambda: _(
        "Give one rate for every other hour, not two"
    ),
    "Bandwidth hours run from 00 to 24, from one hour to another": lambda: _(
        "Bandwidth hours run from 00 to 24, from one hour to another"
    ),
    "An hour is in two bandwidth rules": lambda: _("An hour is in two bandwidth rules"),
}


class BandwidthBody(BaseModel):
    # restate-proxy's grant lines: "08-18 2MiB/s", "20MiB/s"; empty: no limit.
    rules: List[str] = Field(default_factory=list, max_length=limits.MAX_RULES)


@router.put("/backups/targets/{target_id}/proxy-bandwidth")
async def set_proxy_bandwidth(
    target_id: str,
    body: BandwidthBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = _target_or_404(db, target_id)
    try:
        rules = limits.check_rules(body.rules)
    except limits.BandwidthRefused as refused:
        message = _BANDWIDTH_REFUSALS.get(str(refused), lambda: str(refused))()
        raise HTTPException(status_code=422, detail=message) from refused
    if rules and not limits.licensed():
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                "backup_engine",
                _("Bandwidth limits by the hour need the Professional+ backup engine"),
            ),
        )
    target.proxy_bandwidth = json.dumps(rules) if rules else None
    target.updated_at = jobs.now()
    # The storage host rewrites every grant of the target.
    for policy in (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    ):
        policy.config_version += 1
        policy.updated_at = jobs.now()
    _audit(
        db, current_user, EntityType.SETTING, target.id, target.name,
        "Backup target bandwidth limits changed", {"rules": rules},
    )  # fmt: skip
    backup_tick.configure_now(db)
    db.commit()
    return views.target_dict(target, db)
