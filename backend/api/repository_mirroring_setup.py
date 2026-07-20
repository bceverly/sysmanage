# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Setup-status card + platform-config CRUD routes for the Repository Mirroring API.

These endpoint groups were extracted from ``backend.api.repository_mirroring`` to
keep that module under the line-count cap.  They register on the SAME ``router``
object imported from that module, so every route stays registered exactly as
before — ``repository_mirroring`` imports this module at the end of its body to
trigger registration.
"""

from typing import Optional

from fastapi import Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.repository_mirroring import router
from backend.api.repository_mirroring_helpers import (
    _PLATFORM_CONFIG_NOT_FOUND,
    _check_mirror_module,
    _dispatch_plan,
    _parse_uuid,
)
from backend.api.repository_mirroring_schemas import MirrorSetupInstallRequest
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db

# ---------------------------------------------------------------------
# Setup-status card (Phase 10.4.1)
# ---------------------------------------------------------------------
#
# These three routes back the "Mirror Setup Status" card on the
# Repository Mirroring settings tab.  All agent communication goes
# through the existing message queue: the GET returns the cached
# row immediately (or a synthetic ``unknown`` payload when no probe
# has run yet); the two POSTs queue a deployment plan and stamp the
# in-flight message_id.  The agent's command_result lands in
# ``proplus_dispatch._apply_repo_mirror_op_result`` (via the
# ``repo_mirror_op`` correlation registered in ``_dispatch_plan``)
# which clears the message_id and updates the row asynchronously.
# The card polls this GET while ``last_check_message_id`` (or
# ``last_install_message_id``) is non-NULL.


@router.get(
    "/mirror-repositories/setup-status/{host_id}",
    dependencies=[Depends(JWTBearer())],
)
async def get_mirror_setup_status(host_id: str, db: Session = Depends(get_tenant_db)):
    _check_mirror_module()
    pid = _parse_uuid(host_id, "host_id")
    row = (
        db.query(models.MirrorSetupStatus)
        .filter(models.MirrorSetupStatus.host_id == pid)
        .first()
    )
    if row is None:
        # Synthetic "never probed" payload — saves the frontend from
        # branching on 404 vs row.  ``ready_*`` are all false until a
        # probe lands.
        return {
            "host_id": str(pid),
            "tools": {},
            "platform": None,
            "distro": None,
            "last_check_at": None,
            "last_check_message_id": None,
            "last_check_error": None,
            "install_status": "idle",
            "last_install_at": None,
            "last_install_message_id": None,
            "last_install_error": None,
            "ready_apt": False,
            "ready_dnf": False,
            "ready_zypper": False,
            "ready_pkg": False,
        }
    return row.to_dict()


@router.post(
    "/mirror-repositories/setup-status/{host_id}/refresh",
    dependencies=[Depends(JWTBearer())],
)
async def refresh_mirror_setup_status(
    host_id: str, db: Session = Depends(get_tenant_db)
):
    """Queue a tool-presence probe.  The probe's command_result lands
    asynchronously in the inbound queue handler and updates the row.
    """
    engine = _check_mirror_module()
    pid = _parse_uuid(host_id, "host_id")
    plan = engine.build_mirror_setup_check_plan()
    msg_id = _dispatch_plan(plan, pid, action="setup_check", mirror_id="", timeout=60)
    row = (
        db.query(models.MirrorSetupStatus)
        .filter(models.MirrorSetupStatus.host_id == pid)
        .first()
    )
    if row is None:
        row = models.MirrorSetupStatus(host_id=pid)
        db.add(row)
    row.last_check_message_id = msg_id
    db.commit()
    return {"host_id": str(pid), "message_id": msg_id, "status": "dispatched"}


@router.post(
    "/mirror-repositories/setup-install/{host_id}",
    dependencies=[Depends(JWTBearer())],
)
async def install_mirror_tools(
    host_id: str,
    request: MirrorSetupInstallRequest = Body(...),
    db: Session = Depends(get_tenant_db),
):
    """Queue an install plan for the named package manager's mirror tools.
    Result-routing flips ``install_status`` to succeeded / failed and
    auto-chains a setup_check so the card refreshes without manual action.
    """
    engine = _check_mirror_module()
    pid = _parse_uuid(host_id, "host_id")
    try:
        plan = engine.build_mirror_setup_install_plan(request.package_manager)
    except Exception as exc:  # engine raises MirrorConfigError on unknown PM
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    msg_id = _dispatch_plan(
        plan, pid, action="setup_install", mirror_id="", timeout=900
    )
    row = (
        db.query(models.MirrorSetupStatus)
        .filter(models.MirrorSetupStatus.host_id == pid)
        .first()
    )
    if row is None:
        row = models.MirrorSetupStatus(host_id=pid)
        db.add(row)
    row.install_status = "dispatched"
    row.last_install_message_id = msg_id
    row.last_install_error = None
    db.commit()
    return {
        "host_id": str(pid),
        "message_id": msg_id,
        "package_manager": request.package_manager,
        "status": "dispatched",
    }


# ---------------------------------------------------------------------
# Platform-config CRUD (Phase 10.4.2)
# ---------------------------------------------------------------------


_VALID_PLATFORMS = {"apt", "dnf", "zypper", "pkg"}


class PlatformConfigRequest(BaseModel):
    """Body for create / update of a per-platform mirror config."""

    platform: str = Field(..., description="linux | freebsd")
    host_id: str = Field(..., description="UUID of the host that hosts the mirror tree")
    mirror_root_path: Optional[str] = None
    integrity_check_cadence_hours: Optional[int] = Field(None, ge=1, le=168)
    retention_window_days: Optional[int] = Field(None, ge=0, le=365)
    default_bandwidth_cap_kbps: Optional[int] = Field(None, ge=0)
    snapshot_count_to_keep: Optional[int] = Field(None, ge=0, le=100)


@router.get("/mirror-platform-configs", dependencies=[Depends(JWTBearer())])
async def list_platform_configs(db: Session = Depends(get_tenant_db)):
    _check_mirror_module()
    rows = (
        db.query(models.MirrorPlatformConfig)
        .order_by(models.MirrorPlatformConfig.platform)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post("/mirror-platform-configs", dependencies=[Depends(JWTBearer())])
async def create_platform_config(
    request: PlatformConfigRequest = Body(...),
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    _check_mirror_module()
    if request.platform not in _VALID_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid platform: %s") % request.platform,
        )
    host_uuid = _parse_uuid(request.host_id, "host_id")
    host = db.query(models.Host).filter(models.Host.id == host_uuid).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    existing = (
        db.query(models.MirrorPlatformConfig)
        .filter(
            models.MirrorPlatformConfig.platform == request.platform,
            models.MirrorPlatformConfig.host_id == host_uuid,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=_("A platform config for %s on this host already exists")
            % request.platform,
        )
    payload = request.model_dump(exclude_unset=True, exclude={"host_id", "platform"})
    cfg = models.MirrorPlatformConfig(
        platform=request.platform, host_id=host_uuid, **payload
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg.to_dict()


@router.get("/mirror-platform-configs/{cfg_id}", dependencies=[Depends(JWTBearer())])
async def get_platform_config(cfg_id: str, db: Session = Depends(get_tenant_db)):
    _check_mirror_module()
    pid = _parse_uuid(cfg_id, "cfg_id")
    row = (
        db.query(models.MirrorPlatformConfig)
        .filter(models.MirrorPlatformConfig.id == pid)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=_(_PLATFORM_CONFIG_NOT_FOUND))
    return row.to_dict()


@router.put("/mirror-platform-configs/{cfg_id}", dependencies=[Depends(JWTBearer())])
async def update_platform_config(
    cfg_id: str,
    request: PlatformConfigRequest = Body(...),
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    _check_mirror_module()
    pid = _parse_uuid(cfg_id, "cfg_id")
    row = (
        db.query(models.MirrorPlatformConfig)
        .filter(models.MirrorPlatformConfig.id == pid)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=_(_PLATFORM_CONFIG_NOT_FOUND))
    if request.platform not in _VALID_PLATFORMS:
        raise HTTPException(
            status_code=400, detail=_("Invalid platform: %s") % request.platform
        )
    new_host_uuid = _parse_uuid(request.host_id, "host_id")
    if not db.query(models.Host).filter(models.Host.id == new_host_uuid).first():
        raise HTTPException(status_code=404, detail=_("Host not found"))
    row.platform = request.platform
    row.host_id = new_host_uuid
    for field in (
        "mirror_root_path",
        "integrity_check_cadence_hours",
        "retention_window_days",
        "default_bandwidth_cap_kbps",
        "snapshot_count_to_keep",
    ):
        value = getattr(request, field)
        if value is not None:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.delete("/mirror-platform-configs/{cfg_id}", dependencies=[Depends(JWTBearer())])
async def delete_platform_config(
    cfg_id: str,
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    _check_mirror_module()
    pid = _parse_uuid(cfg_id, "cfg_id")
    row = (
        db.query(models.MirrorPlatformConfig)
        .filter(models.MirrorPlatformConfig.id == pid)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=_(_PLATFORM_CONFIG_NOT_FOUND))
    # Refuse to delete a config that still owns mirrors — caller has to
    # delete or reassign the mirrors first.
    in_use = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.platform_config_id == pid)
        .count()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=_("Platform config still owns %d mirror(s); delete those first")
            % in_use,
        )
    db.delete(row)
    db.commit()
    return {"deleted": str(pid)}
