# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Repository Mirroring API (Phase 10.4 + 10.4.2 + 10.4.3 + 10.4.4).

Thin OSS routes that gate on the Pro+ ``repository_mirroring_engine``
module — when it isn't loaded, every endpoint returns 402.  When it
is loaded, plan-builders in the engine produce the
``apply_deployment_plan`` payloads that the agent on the mirror host
executes.

Routes:

  GET    /api/v1/mirror-repositories                — list mirrors (?platform_config_id filter)
  POST   /api/v1/mirror-repositories                — create
  GET    /api/v1/mirror-repositories/{id}           — get one
  PUT    /api/v1/mirror-repositories/{id}           — update
  DELETE /api/v1/mirror-repositories/{id}           — delete
  POST   /api/v1/mirror-repositories/{id}/sync      — fire sync NOW
  POST   /api/v1/mirror-repositories/{id}/snapshot  — take a snapshot
  POST   /api/v1/mirror-repositories/{id}/restore/{snapshot_id} — restore
  GET    /api/v1/mirror-repositories/{id}/snapshots — list snapshots
  POST   /api/v1/mirror-repositories/tick           — sync-due driver hook
  GET    /api/v1/settings/mirror                    — singleton settings (legacy)
  PUT    /api/v1/settings/mirror                    — singleton update (legacy)

Phase 10.4.2 — per-platform configs (replaces the singleton settings
as the source of truth for filesystem + retention defaults):

  GET    /api/v1/mirror-platform-configs            — list (one per platform)
  POST   /api/v1/mirror-platform-configs            — create or upsert
  GET    /api/v1/mirror-platform-configs/{id}       — get one
  PUT    /api/v1/mirror-platform-configs/{id}       — update
  DELETE /api/v1/mirror-platform-configs/{id}       — delete (cascades repos to NULL)

Phase 10.4.1 — per-host setup status / install routes (still keyed by
host_id since "is apt-mirror installed on this host" is a host-level
question, not a platform-level one):

  GET    /api/v1/mirror-repositories/setup-status/{host_id}
  POST   /api/v1/mirror-repositories/setup-status/{host_id}/refresh
  POST   /api/v1/mirror-repositories/setup-install/{host_id}
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import (
    get_shared_db,
    get_tenant_db,
    iter_host_databases,
    shared_sessionmaker,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Helpers + shared constants and the Pydantic request models live in sibling
# modules (extracted to keep this file under the line-count cap); re-imported
# here so this module's public surface is unchanged.
from backend.api.repository_mirroring_helpers import (  # pylint: disable=unused-import,wrong-import-position
    _MIRROR_MAX_SYNC_FAILURES,
    _MIRROR_NOT_FOUND,
    _PLATFORM_CONFIG_NOT_FOUND,
    _check_mirror_module,
    _config_from_row,
    _dispatch_plan,
    _get_settings,
    _parse_uuid,
    _platform_for_pm,
    _tick_mirrors_one_db,
)
from backend.api.repository_mirroring_schemas import (  # pylint: disable=unused-import,wrong-import-position
    MirrorCreateRequest,
    MirrorSettingsRequest,
    MirrorSetupInstallRequest,
    MirrorUpdateRequest,
)

# ---------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------


@router.get("/mirror-repositories", dependencies=[Depends(JWTBearer())])
async def list_mirrors(
    platform_config_id: Optional[str] = None, db: Session = Depends(get_tenant_db)
):
    _check_mirror_module()
    q = db.query(models.MirrorRepository)
    if platform_config_id:
        cfg_uuid = _parse_uuid(platform_config_id, "platform_config_id")
        q = q.filter(models.MirrorRepository.platform_config_id == cfg_uuid)
    rows = q.order_by(models.MirrorRepository.name).all()
    return [r.to_dict() for r in rows]


@router.post("/mirror-repositories", dependencies=[Depends(JWTBearer())])
async def create_mirror(
    request: MirrorCreateRequest,
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    engine = _check_mirror_module()
    try:
        engine.validate_mirror_config(request.model_dump())
    except engine.MirrorConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    host_uuid = _parse_uuid(request.host_id, "host_id")
    host = db.query(models.Host).filter(models.Host.id == host_uuid).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Mirror host not found"))

    # Phase 10.4.2 — every new mirror lives under a platform_config.
    # If one already exists for this (host, derived_platform) pair we
    # reuse it; otherwise we auto-create one with engine defaults so
    # the table is never the source of unparented rows.
    platform = _platform_for_pm(request.package_manager)
    cfg = (
        db.query(models.MirrorPlatformConfig)
        .filter(
            models.MirrorPlatformConfig.host_id == host_uuid,
            models.MirrorPlatformConfig.platform == platform,
        )
        .first()
    )
    if cfg is None:
        cfg = models.MirrorPlatformConfig(host_id=host_uuid, platform=platform)
        db.add(cfg)
        db.flush()  # need cfg.id

    row = models.MirrorRepository(
        name=request.name,
        package_manager=request.package_manager,
        upstream_url=request.upstream_url,
        suite=request.suite,
        components=request.components,
        architectures=request.architectures,
        repoid=request.repoid,
        gpgkey_url=request.gpgkey_url,
        repo_alias=request.repo_alias,
        release=request.release,
        signing_key_url=request.signing_key_url,
        bandwidth_cap_kbps=request.bandwidth_cap_kbps,
        sync_cron=request.sync_cron,
        network_tier=request.network_tier,
        enabled=request.enabled,
        host_id=host_uuid,
        platform_config_id=cfg.id,
        known_version_id=(
            _parse_uuid(request.known_version_id, "known_version_id")
            if request.known_version_id
            else None
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.get("/mirror-repositories/{mirror_id}", dependencies=[Depends(JWTBearer())])
async def get_mirror(mirror_id: str, db: Session = Depends(get_tenant_db)):
    _check_mirror_module()
    pid = _parse_uuid(mirror_id, "mirror_id")
    row = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == pid)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_(_MIRROR_NOT_FOUND))
    return row.to_dict()


@router.put("/mirror-repositories/{mirror_id}", dependencies=[Depends(JWTBearer())])
async def update_mirror(
    mirror_id: str,
    request: MirrorUpdateRequest,
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    _check_mirror_module()
    pid = _parse_uuid(mirror_id, "mirror_id")
    row = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == pid)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_(_MIRROR_NOT_FOUND))
    for field, value in request.model_dump(exclude_unset=True).items():
        if field == "known_version_id" and value:
            value = _parse_uuid(value, "known_version_id")
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.delete("/mirror-repositories/{mirror_id}", dependencies=[Depends(JWTBearer())])
async def delete_mirror(
    mirror_id: str,
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    _check_mirror_module()
    pid = _parse_uuid(mirror_id, "mirror_id")
    row = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == pid)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_(_MIRROR_NOT_FOUND))
    db.delete(row)
    db.commit()
    return {"message": _("Mirror deleted"), "id": mirror_id}


# ---------------------------------------------------------------------
# Operations: sync / snapshot / restore / list-snapshots / tick
# ---------------------------------------------------------------------


@router.post(
    "/mirror-repositories/{mirror_id}/sync", dependencies=[Depends(JWTBearer())]
)
async def sync_mirror(mirror_id: str, db: Session = Depends(get_tenant_db)):
    engine = _check_mirror_module()
    pid = _parse_uuid(mirror_id, "mirror_id")
    row = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == pid)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_(_MIRROR_NOT_FOUND))
    settings = _get_settings(db)
    config = _config_from_row(row)
    builder = {
        "apt": engine.build_apt_mirror_sync_plan,
        "dnf": engine.build_dnf_mirror_sync_plan,
        "zypper": engine.build_zypper_mirror_sync_plan,
        "pkg": engine.build_pkg_mirror_sync_plan,
    }.get(row.package_manager)
    if builder is None:
        raise HTTPException(
            status_code=400,
            detail=_("Unsupported package_manager: %s") % row.package_manager,
        )
    plan = builder(config, settings.mirror_root_path)
    msg_id = _dispatch_plan(plan, row.host_id, action="sync", mirror_id=str(row.id))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row.last_sync_at = now
    row.last_sync_status = "DISPATCHED"
    row.last_sync_error = None
    # Stamp the in-flight marker so the UI can render
    # "syncing since N minutes ago" until the result handler clears it.
    row.last_sync_message_id = msg_id
    db.commit()
    return {
        "message": _("Mirror sync dispatched"),
        "mirror_id": mirror_id,
        "message_id": msg_id,
    }


@router.post(
    "/mirror-repositories/{mirror_id}/snapshot", dependencies=[Depends(JWTBearer())]
)
async def snapshot_mirror(mirror_id: str, db: Session = Depends(get_tenant_db)):
    engine = _check_mirror_module()
    pid = _parse_uuid(mirror_id, "mirror_id")
    row = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == pid)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_(_MIRROR_NOT_FOUND))
    settings = _get_settings(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    plan = engine.build_mirror_snapshot_plan(
        _config_from_row(row), settings.mirror_root_path, snapshot_id
    )
    msg_id = _dispatch_plan(
        plan, row.host_id, action="snapshot", mirror_id=str(row.id), timeout=600
    )
    # Eagerly insert the snapshot row so the UI's expand-row can show
    # "snapshot in progress" immediately; the result handler later
    # populates size_bytes / file_count on success or deletes the row
    # on failure (so the list doesn't accumulate phantom snapshots).
    snap = models.MirrorSnapshot(
        repository_id=row.id,
        snapshot_id=snapshot_id,
        taken_at=now,
    )
    db.add(snap)
    row.last_snapshot_at = now
    row.last_snapshot_status = "DISPATCHED"
    row.last_snapshot_error = None
    row.last_snapshot_message_id = msg_id
    db.commit()
    return {"snapshot_id": snapshot_id, "message_id": msg_id}


@router.post(
    "/mirror-repositories/{mirror_id}/restore/{snapshot_id}",
    dependencies=[Depends(JWTBearer())],
)
async def restore_mirror(
    mirror_id: str, snapshot_id: str, db: Session = Depends(get_tenant_db)
):
    engine = _check_mirror_module()
    pid = _parse_uuid(mirror_id, "mirror_id")
    row = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == pid)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_(_MIRROR_NOT_FOUND))
    settings = _get_settings(db)
    plan = engine.build_mirror_restore_plan(
        _config_from_row(row), settings.mirror_root_path, snapshot_id
    )
    msg_id = _dispatch_plan(
        plan, row.host_id, action="restore", mirror_id=str(row.id), timeout=600
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row.last_restore_at = now
    row.last_restore_status = "DISPATCHED"
    row.last_restore_error = None
    row.last_restore_message_id = msg_id
    db.commit()
    return {"snapshot_id": snapshot_id, "message_id": msg_id}


@router.get(
    "/mirror-repositories/{mirror_id}/snapshots",
    dependencies=[Depends(JWTBearer())],
)
async def list_snapshots(mirror_id: str, db: Session = Depends(get_tenant_db)):
    _check_mirror_module()
    pid = _parse_uuid(mirror_id, "mirror_id")
    rows = (
        db.query(models.MirrorSnapshot)
        .filter(models.MirrorSnapshot.repository_id == pid)
        .order_by(models.MirrorSnapshot.taken_at.desc())
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post("/mirror-repositories/tick", dependencies=[Depends(JWTBearer())])
async def tick_mirrors():
    """Driver hook for an external scheduler.  Selects every enabled
    mirror with ``next_sync_at <= now`` (or NULL) and dispatches a
    sync plan for it.  Recomputes ``next_sync_at`` from the cron.
    Idempotent within a single tick — running twice is a no-op once
    next_sync_at has been pushed forward.

    Phase 13.1: there's no logged-in user / active-tenant context here (an
    external scheduler drives this), so — like the heartbeat sweep — it fans
    out across EVERY host database via ``iter_host_databases()``: the bootstrap
    DB plus each provisioned tenant DB.  A tenant host's mirror rows live in its
    tenant database, so the bootstrap pass alone would never see them.  One bad
    tenant DB is logged and skipped without stalling the rest of the sweep.
    """
    engine = _check_mirror_module()
    automation = module_loader.get_module("automation_engine")
    if automation is None:
        raise HTTPException(
            status_code=502,
            detail=_("Mirror tick requires automation_engine for cron evaluation."),
        )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fired = []
    disabled = []
    for label, _tenant_id, session in iter_host_databases():
        try:
            db_fired, db_disabled = _tick_mirrors_one_db(
                session, engine, automation, now
            )
            fired.extend(db_fired)
            disabled.extend(db_disabled)
        except Exception:  # pylint: disable=broad-exception-caught
            session.rollback()
            logger.exception("Mirror tick failed for database %s", label)
        finally:
            session.close()
    return {
        "fired_count": len(fired),
        "fired": fired,
        "disabled_count": len(disabled),
        "disabled": disabled,
    }


# ---------------------------------------------------------------------
# Admin settings (singleton)
# ---------------------------------------------------------------------


@router.get("/settings/mirror", dependencies=[Depends(JWTBearer())])
async def get_mirror_settings(db: Session = Depends(get_tenant_db)):
    _check_mirror_module()
    return _get_settings(db).to_dict()


@router.put("/settings/mirror", dependencies=[Depends(JWTBearer())])
async def update_mirror_settings(
    request: MirrorSettingsRequest = Body(...),
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    _check_mirror_module()
    row = _get_settings(db)
    if row not in db:
        db.add(row)
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row.to_dict()


# ---------------------------------------------------------------------
# Known versions (Phase 10.4.4) — sourced from a pre-populated catalog
# so the Add Mirror dialog uses a dropdown instead of free-text and
# operators can't fat-finger ``noblee`` and silently break a mirror.
# ---------------------------------------------------------------------


@router.get("/mirror-known-versions", dependencies=[Depends(JWTBearer())])
async def list_known_versions(
    platform: Optional[str] = None, db: Session = Depends(get_shared_db)
):
    # Phase 13.1.D: the catalog is shared reference data, so read it from the
    # shared partition rather than the active tenant's database.
    _check_mirror_module()
    q = db.query(models.MirrorKnownVersion).filter(
        models.MirrorKnownVersion.is_active.is_(True)
    )
    if platform:
        q = q.filter(models.MirrorKnownVersion.platform == platform)
    return [r.to_dict() for r in q.order_by(models.MirrorKnownVersion.label).all()]


# ---------------------------------------------------------------------
# Host-default-mirror assignments (Phase 10.4.4)
# ---------------------------------------------------------------------


def _hosts_matching_version(db: Session, kv: "models.MirrorKnownVersion"):
    """Find every active host whose platform_release matches the
    catalog's match_regex.  Used when an admin (un)assigns a default
    mirror — we need to dispatch apply or revert plans for each.
    Case-insensitive Python regex; the catalog stores patterns as
    plain strings."""
    import re

    try:
        rx = re.compile(kv.match_regex, re.IGNORECASE)
    except re.error:
        return []
    rows = db.query(models.Host).filter(models.Host.active.is_(True)).all()
    out = []
    for h in rows:
        # ReDoS defense-in-depth: cap input length so a pathological
        # ``match_regex`` (admin-curated, but treat as untrusted)
        # can't run unbounded on a long platform_release string.
        # platform_release / platform_version are agent-reported but
        # constrained to ~200 chars in practice.
        text = ((h.platform_release or "") + " " + (h.platform_version or ""))[:512]
        # nosemgrep: python.fastapi.regex.tainted-regex-stdlib-fastapi.tainted-regex-stdlib-fastapi
        if rx.search(text):
            out.append(h)
    return out


def _legacy_field_match(mirror, kv) -> bool:
    """Legacy free-text fallback for mirrors that pre-date the
    known_version_id FK.  Matches the catalog's default value against
    the appropriate per-PM column."""
    field_map = {
        "apt": (mirror.suite, kv.default_suite),
        "dnf": (mirror.repoid, kv.default_repoid),
        "zypper": (mirror.repo_alias, kv.default_repo_alias),
        "pkg": (mirror.release, kv.default_release),
    }
    mv, kvv = field_map.get(kv.platform, (None, None))
    return bool(mv and kvv and mv == kvv)


def _eligible_mirrors_for_version(db: Session, kv) -> list[dict]:
    """Return the {id,name} list of mirrors that match the catalog row
    by FK (or legacy free-text) and have synced successfully."""
    candidates = (
        db.query(models.MirrorRepository)
        .filter(
            models.MirrorRepository.package_manager == kv.platform,
            models.MirrorRepository.last_sync_status == "SUCCESS",
        )
        .all()
    )
    return [
        {"id": str(m.id), "name": m.name}
        for m in candidates
        if m.known_version_id == kv.id or _legacy_field_match(m, kv)
    ]


def _assignment_row(kv, cur, eligible: list[dict]) -> dict:
    """Shape a single response row for the assignments endpoint."""
    return {
        "platform": kv.platform,
        "version_key": kv.version_key,
        "os_family": kv.os_family,
        "label": kv.label,
        "match_regex": kv.match_regex,
        "eligible_mirrors": eligible,
        "current_mirror_id": (str(cur.mirror_id) if cur and cur.mirror_id else None),
        "assignment_id": str(cur.id) if cur else None,
        "updated_at": (cur.updated_at.isoformat() if cur and cur.updated_at else None),
    }


@router.get("/host-defaults/mirrors", dependencies=[Depends(JWTBearer())])
async def list_default_mirror_assignments(
    db: Session = Depends(get_tenant_db),
    shared_db: Session = Depends(get_shared_db),
):
    """Return one row per (platform, version_key, os_family) tuple
    drawn from the known-versions catalog, with the currently-assigned
    mirror_id (or null = "Cloud") and the list of mirrors that are
    eligible to be assigned (right PM + matching default values +
    last_sync_status == 'SUCCESS')."""
    _check_mirror_module()
    # Phase 13.1.D: the catalog is shared reference data; the assignments and
    # eligible mirrors are tenant data. Read each from its own partition.
    versions = (
        shared_db.query(models.MirrorKnownVersion)
        .filter(models.MirrorKnownVersion.is_active.is_(True))
        .order_by(
            models.MirrorKnownVersion.platform,
            models.MirrorKnownVersion.label,
        )
        .all()
    )
    assignments = {
        (a.platform, a.version_key, a.os_family): a
        for a in db.query(models.HostDefaultMirror).all()
    }
    return [
        _assignment_row(
            kv,
            assignments.get((kv.platform, kv.version_key, kv.os_family)),
            _eligible_mirrors_for_version(db, kv),
        )
        for kv in versions
    ]


class HostDefaultMirrorRequest(BaseModel):
    """Body for assigning a mirror (or null for "Cloud") to a
    (platform, version_key, os_family) tuple."""

    mirror_id: Optional[str] = None


def _resolve_assignment_mirror(db: Session, request, platform: str):
    """Look up + validate the mirror referenced by an assignment
    request.  Returns None for the cloud-revert case; raises
    HTTPException for any validation failure."""
    if not request.mirror_id:
        return None
    mirror_uuid = _parse_uuid(request.mirror_id, "mirror_id")
    mirror = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == mirror_uuid)
        .first()
    )
    if mirror is None:
        raise HTTPException(status_code=404, detail=_(_MIRROR_NOT_FOUND))
    if mirror.last_sync_status != "SUCCESS":
        raise HTTPException(
            status_code=409,
            detail=_(
                "Mirror %s has not completed a successful sync yet — "
                "wait for sync to succeed before assigning it as a default."
            )
            % mirror.name,
        )
    if mirror.package_manager != platform:
        raise HTTPException(
            status_code=400,
            detail=_(
                "Mirror %(mirror_name)s is for %(package_manager)s, "
                "can't assign to a %(platform)s default"
            )
            % {
                "mirror_name": mirror.name,
                "package_manager": mirror.package_manager,
                "platform": platform,
            },
        )
    return mirror


def _upsert_assignment_row(db: Session, platform, version_key, os_family, new_mirror):
    """Create-or-update the HostDefaultMirror row, returning
    (row, previous_mirror_id)."""
    row = (
        db.query(models.HostDefaultMirror)
        .filter(
            models.HostDefaultMirror.platform == platform,
            models.HostDefaultMirror.version_key == version_key,
            models.HostDefaultMirror.os_family == os_family,
        )
        .first()
    )
    if row is None:
        row = models.HostDefaultMirror(
            platform=platform, version_key=version_key, os_family=os_family
        )
        db.add(row)
    previous_mirror_id = row.mirror_id
    row.mirror_id = new_mirror.id if new_mirror else None
    db.commit()
    db.refresh(row)
    return row, previous_mirror_id


def _dispatch_default_mirror_change(engine, kv, new_mirror, db: Session) -> list[dict]:
    """Queue apply or revert plans for every matching host.  Returns
    the dispatched-message list for the API response."""
    action = "default_apply" if new_mirror else "default_revert"
    dispatched = []
    for host in _hosts_matching_version(db, kv):
        plan = _default_mirror_plan_for(engine, kv, new_mirror)
        if plan is None:
            continue
        msg_id = _dispatch_plan(plan, host.id, action=action, mirror_id="", timeout=300)
        dispatched.append({"host_id": str(host.id), "message_id": msg_id})
    return dispatched


@router.put(
    "/host-defaults/mirrors/{platform}/{version_key}/{os_family}",
    dependencies=[Depends(JWTBearer())],
)
async def set_default_mirror_assignment(
    platform: str,
    version_key: str,
    os_family: str,
    request: HostDefaultMirrorRequest = Body(...),
    db: Session = Depends(get_tenant_db),
    shared_db: Session = Depends(get_shared_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    """Assign (or unassign) a default mirror for a known (platform,
    version_key, os_family) tuple.  Hard-blocks if the mirror hasn't
    completed a successful sync.  Queues apply or revert plans for
    every active host whose platform_release matches the catalog's
    regex — simultaneous rollout, no staggered windows.  Returns the
    list of dispatched message_ids so the UI can poll completion."""
    engine = _check_mirror_module()
    # Phase 13.1.D: catalog row from the shared partition; everything else
    # (assignment row, mirror, matching hosts) is tenant data on ``db``.
    kv = (
        shared_db.query(models.MirrorKnownVersion)
        .filter(
            models.MirrorKnownVersion.platform == platform,
            models.MirrorKnownVersion.version_key == version_key,
            models.MirrorKnownVersion.os_family == os_family,
        )
        .first()
    )
    if kv is None:
        raise HTTPException(
            status_code=404, detail=_("Unknown (platform, version, os_family) tuple")
        )
    new_mirror = _resolve_assignment_mirror(db, request, platform)
    row, previous_mirror_id = _upsert_assignment_row(
        db, platform, version_key, os_family, new_mirror
    )
    dispatched = _dispatch_default_mirror_change(engine, kv, new_mirror, db)
    return {
        "platform": platform,
        "version_key": version_key,
        "os_family": os_family,
        "mirror_id": str(row.mirror_id) if row.mirror_id else None,
        "previous_mirror_id": str(previous_mirror_id) if previous_mirror_id else None,
        "dispatched": dispatched,
    }


def _resolve_mirror_url(mirror) -> str:
    """Look up the mirror host's fqdn and return the over-HTTP URL.
    The mirror host's agent serves ``<mirror_root_path>/<name>`` at
    ``/mirror/<name>``; client hosts pull from there."""
    from backend.persistence.db import get_session_local  # avoid top-level cycle

    session_local = get_session_local()
    with session_local() as session:
        mirror_host_row = (
            session.query(models.Host).filter(models.Host.id == mirror.host_id).first()
        )
        fqdn = mirror_host_row.fqdn if mirror_host_row else "localhost"
    # Rationale: package mirrors serve over HTTP intentionally.  apt/dnf/
    # zypper/pkg verify repository metadata via gpg signatures (apt-secure,
    # dnf gpgcheck, zypper rpm-key, pkg PUBKEY) independently of transport;
    # forcing https here would require provisioning a TLS cert on every
    # mirror host's local agent, which the project does not do.
    #
    # SSRF note: ``fqdn`` comes from ``models.Host.fqdn`` of the row
    # whose ``id == mirror.host_id``.  Host records are admin-curated
    # (created via the host registration flow); mirror.host_id is set
    # by the operator when defining the mirror in Settings → Repository
    # Mirroring.  The URL is consumed by the agent's apt/dnf config —
    # never by a request handler that proxies to it — so even a
    # compromised host_id would only point the AGENT at a bad mirror,
    # not enable SSRF from the SERVER.
    # nosemgrep: python.django.security.injection.tainted-url-host.tainted-url-host
    return f"http://{fqdn}/mirror/{mirror.name}"  # NOSONAR


# PM → revert-plan-builder dispatch.  Each lambda takes (engine, kv)
# and returns a plan dict.  Keeps cognitive complexity of
# ``_default_mirror_plan_for`` flat.
_REVERT_BUILDERS = {
    "apt": lambda eng, kv: eng.build_apt_revert_default_mirror_plan(),
    "dnf": lambda eng, kv: eng.build_dnf_revert_default_mirror_plan(
        kv.default_repoid or ""
    ),
    "zypper": lambda eng, kv: eng.build_zypper_revert_default_mirror_plan(
        kv.default_repo_alias or ""
    ),
    "pkg": lambda eng, kv: eng.build_pkg_revert_default_mirror_plan(),
}

# PM → apply-plan-builder dispatch.  Each lambda takes
# (engine, kv, mirror, mirror_url).
_APPLY_BUILDERS = {
    "apt": lambda eng, kv, m, url: eng.build_apt_apply_default_mirror_plan(
        url, m.suite or kv.default_suite or "", m.components or "main"
    ),
    "dnf": lambda eng, kv, m, url: eng.build_dnf_apply_default_mirror_plan(
        m.repoid or kv.default_repoid or "", url, m.gpgkey_url or ""
    ),
    "zypper": lambda eng, kv, m, url: eng.build_zypper_apply_default_mirror_plan(
        m.repo_alias or kv.default_repo_alias or "", url
    ),
    "pkg": lambda eng, kv, m, url: eng.build_pkg_apply_default_mirror_plan(url),
}


def _default_mirror_plan_for(
    engine, kv: "models.MirrorKnownVersion", mirror
) -> Optional[dict]:
    """Build the apply or revert plan for a single host, given the
    catalog row + the chosen mirror (or None for revert).  Returns
    None when no plan applies (e.g., zypper revert without an alias
    in the catalog — shouldn't happen for seeded rows)."""
    if mirror is None:
        builder = _REVERT_BUILDERS.get(kv.platform)
        return builder(engine, kv) if builder else None
    builder = _APPLY_BUILDERS.get(kv.platform)
    if builder is None:
        return None
    return builder(engine, kv, mirror, _resolve_mirror_url(mirror))


def apply_default_mirrors_for_new_host(host_id: str) -> List[dict]:
    """Registration hook — called when a host first comes active.  For
    every (platform, version_key, os_family) assignment whose match
    regex covers this host, queue an apply plan so the host points
    at the mirror without operator action.  Returns the list of
    dispatched plans."""
    import re

    from backend.persistence.db import get_session_local

    session_local = get_session_local()
    dispatched = []
    with session_local() as session:
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if host is None:
            return []
        engine = module_loader.get_module("repository_mirroring_engine")
        if engine is None:
            return []
        text = (host.platform_release or "") + " " + (host.platform_version or "")
        # Phase 13.1.D: the assignments are tenant data but the catalog is shared
        # reference data in a different partition, so this can no longer be a SQL
        # join. Pull the assignments from the tenant session and the catalog from
        # a shared session, then join them in Python on
        # (platform, version_key, os_family).
        assignments = (
            session.query(models.HostDefaultMirror)
            .filter(models.HostDefaultMirror.mirror_id.isnot(None))
            .all()
        )
        with shared_sessionmaker()() as shared_session:
            catalog = {
                (kv.platform, kv.version_key, kv.os_family): kv
                for kv in shared_session.query(models.MirrorKnownVersion).all()
            }
        rows = [
            (assignment, catalog[key])
            for assignment in assignments
            for key in [
                (assignment.platform, assignment.version_key, assignment.os_family)
            ]
            if key in catalog
        ]
        for assignment, kv in rows:
            try:
                rx = re.compile(kv.match_regex, re.IGNORECASE)
            except re.error:
                continue
            if not rx.search(text):
                continue
            mirror = (
                session.query(models.MirrorRepository)
                .filter(models.MirrorRepository.id == assignment.mirror_id)
                .first()
            )
            if mirror is None:
                continue
            plan = _default_mirror_plan_for(engine, kv, mirror)
            if plan is None:
                continue
            msg_id = _dispatch_plan(
                plan, host.id, action="default_apply", mirror_id="", timeout=300
            )
            dispatched.append(
                {
                    "platform": kv.platform,
                    "version_key": kv.version_key,
                    "message_id": msg_id,
                }
            )
    return dispatched


# The setup-status card + platform-config CRUD endpoint groups live in a sibling
# module (extracted to keep this file under the line-count cap).  Importing it
# here — after ``router`` is defined and all other routes are registered —
# registers those routes on the SAME ``router`` object, so every route that
# existed before is still registered identically.
from backend.api import (  # pylint: disable=wrong-import-position,unused-import
    repository_mirroring_setup,
)
