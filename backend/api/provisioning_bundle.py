# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Provisioning bundle API (Phase 18.1 S4).

OSS orchestration: mint a tenant enrollment token (optionally carrying site /
access-group placement) and render a ready-to-embed cloud-init ``user-data``
blob that makes a freshly-booted host install the agent and auto-enroll into
that tenant/site.  This is the seam an EXTERNAL provisioner (PXE / MAAS /
Terraform / a golden image) uses — the in-app provision wizard builds its own
seed inline.

Reuses the Pro+ ``provisioning_engine`` render helpers (the moat) + the
``multitenancy_engine`` enrollment-token logic (via ``enrollment_service``).
Gated behind the Enterprise ``PROVISIONING_MANAGE`` feature.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config
from backend.i18n import _
from backend.licensing.features import FeatureCode, ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.services import enrollment_service

router = APIRouter(dependencies=[Depends(JWTBearer())])

# Default agent-install for the common cloud image (Ubuntu/Debian).  Per-distro
# dispatch is a follow-up; a cloud-init template can override the whole blob.
_DEFAULT_INSTALL: List[str] = [
    "add-apt-repository -y ppa:bceverly/sysmanage-agent",
    "apt-get update",
    "apt-get install -y sysmanage-agent",
]


class ProvisioningBundleRequest(BaseModel):
    tenant_id: str
    # Optional placement baked into the minted token.
    site_id: Optional[str] = None
    access_group_id: Optional[str] = None
    # Where the provisioned host phones home.
    server_host: str
    server_port: int = 8080
    use_https: bool = True
    hostname: Optional[str] = None
    registration_key: Optional[str] = None
    # OS family of the target image (debian/ubuntu, rhel, fedora, suse, arch,
    # alpine, freebsd) selecting the per-distro agent-install recipe; defaults
    # to debian/ubuntu when omitted.
    os_family: Optional[str] = None
    # Token bounds (mirrors the control-plane token create).
    label: Optional[str] = None
    expires_in_days: Optional[int] = None
    max_uses: Optional[int] = None


class ProvisioningBundleResponse(BaseModel):
    # The plaintext enrollment token — embedded in user_data + returned once.
    token: str
    hostname: str
    user_data: str


def _require_provisioning_license() -> None:
    if not license_service.has_feature(FeatureCode.PROVISIONING_MANAGE):
        raise HTTPException(
            status_code=402,
            detail=_("Provisioning requires a SysManage Enterprise license."),
        )


def _provisioning_engine():
    """Return the loaded provisioning_engine (for the render helpers)."""
    if not license_service.has_module(ModuleCode.PROVISIONING_ENGINE):
        raise HTTPException(
            status_code=402,
            detail=_("Provisioning requires a SysManage Enterprise license."),
        )
    engine = module_loader.get_module("provisioning_engine")
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail=_("The provisioning module is not currently available."),
        )
    return engine


def _expires_at(expires_in_days: Optional[int]) -> Optional[datetime]:
    if expires_in_days is None:
        return None
    if expires_in_days > 3650:
        raise HTTPException(
            status_code=400,
            detail=_("expires_in_days must be 3650 (10 years) or fewer."),
        )
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        days=expires_in_days
    )


@router.post("/provisioning/bundle", response_model=ProvisioningBundleResponse)
async def create_provisioning_bundle(
    body: ProvisioningBundleRequest,
    current_user=Depends(get_current_user),
):
    """Mint a placement-bearing enrollment token + render first-boot user-data.

    The plaintext token is shown ONCE (embedded in ``user_data`` and returned);
    it is never retrievable again.
    """
    _require_provisioning_license()
    if not config.is_multitenancy_enabled():
        raise HTTPException(
            status_code=400,
            detail=_("Enrollment tokens require multi-tenancy to be enabled."),
        )
    engine = _provisioning_engine()

    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )

    expires_at = _expires_at(body.expires_in_days)
    try:
        with partition_session(partition=PARTITION_REGISTRY) as session:
            plaintext, _row = enrollment_service.generate_token(
                session,
                body.tenant_id,
                label=body.label,
                expires_at=expires_at,
                max_uses=body.max_uses,
                created_by=current_user,
                site_id=body.site_id,
                access_group_id=body.access_group_id,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # A bad tenant_id (FK) or an unloaded engine surfaces here.
        raise HTTPException(
            status_code=400,
            detail=_("Could not mint an enrollment token for that tenant."),
        ) from exc

    hostname = body.hostname or "sysmanage-host"
    agent_yaml = engine.render_agent_config_yaml(
        body.server_host,
        body.server_port,
        body.use_https,
        enrollment_token=plaintext,
        registration_key=body.registration_key or "",
    )
    # Per-distro agent-install (Phase 18.1): the engine builds the full runcmd
    # sequence for the target OS family.  Guarded so an older engine .so (no
    # dispatch fn, render bakes the systemd install) still works during a
    # rebuild window.
    if hasattr(engine, "agent_install_runcmd"):
        runcmd = engine.agent_install_runcmd(body.os_family or "")
        user_data = engine.render_cloud_init_user_data(hostname, agent_yaml, runcmd)
    else:
        user_data = engine.render_cloud_init_user_data(
            hostname, agent_yaml, list(_DEFAULT_INSTALL)
        )
    return ProvisioningBundleResponse(
        token=plaintext, hostname=hostname, user_data=user_data
    )
