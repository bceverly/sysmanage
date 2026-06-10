"""
Air-gap collector one-shot runs API (Phase 11).

Companion to ``airgap_collection_schedule.py`` (which handles cron-driven
recurring runs).  This module exposes the surface the operator UI needs:
create a one-shot collection run, list / inspect prior runs, fetch the
produced media manifests, and stream the signed ISO back to the browser.

Routes are gated on ``airgap_collector_engine`` being loaded — the engine
being available is the Pro+ + role-collector check.  The actual run
processing (mirroring, ISO build, signing) is handled by the engine's
background worker; this module only manages the row lifecycle and serves
the artifact.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import List, Optional

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.auth.auth_handler import (
    decode_airgap_download_token,
    sign_airgap_download_token,
)
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.audit_service import (
    ActionType,
    AuditService,
    EntityType,
    Result,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/airgap/collector",
    tags=["airgap-collector-runs"],
    dependencies=[Depends(JWTBearer())],
)

# Separate router WITHOUT the blanket JWTBearer header dependency, for the
# streaming ISO download only.  A browser following a plain download link
# can't supply the Authorization header, so this route authenticates via a
# short-lived, single-run download token in the query string (minted by the
# authenticated POST /runs/{id}/iso-token below).  Everything else stays on
# the header-authenticated ``router``.
download_router = APIRouter(
    prefix="/api/v1/airgap/collector",
    tags=["airgap-collector-runs"],
)


_ERR_RUN_NOT_FOUND = "Air-gap collection run not found"
_ERR_MANIFEST_NOT_FOUND = "Air-gap media manifest not found"
_ERR_INVALID_RUN_UUID = "Invalid UUID for run_id: %s"
_ERR_INVALID_MANIFEST_UUID = "Invalid UUID for manifest_id: %s"


def _check_collector_module():
    engine = module_loader.get_module("airgap_collector_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Air-gap collection runs require a SysManage Professional+ "
                "license with the air-gap collector engine. Please upgrade to "
                "access this feature."
            ),
        )
    return engine


def _get_user(db: Session, current_user: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


def _parse_run_uuid(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_(_ERR_INVALID_RUN_UUID) % run_id,
        ) from exc


def _parse_manifest_uuid(manifest_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(manifest_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_(_ERR_INVALID_MANIFEST_UUID) % manifest_id,
        ) from exc


class RunTargetSpec(BaseModel):
    """One target inside a collection run.

    Option-B input shape: the operator picks a configured mirror by id
    and the server derives distro / version from the mirror's
    metadata.  The orchestrator pins a specific snapshot of that
    mirror at QUEUED → MIRRORING — the bundle is then byte-for-byte
    that snapshot's tree.

    ``mirror_id`` is required on input.  ``distro``, ``version``,
    ``mirror_name`` are server-populated on output for display; clients
    sending these on input are ignored.
    """

    mirror_id: str = Field(..., min_length=1, max_length=80)
    distro: Optional[str] = Field(default=None, max_length=40)
    version: Optional[str] = Field(default=None, max_length=40)
    repos: List[str] = Field(default_factory=list)
    mirror_name: Optional[str] = Field(default=None, max_length=200)
    source_snapshot_id: Optional[str] = Field(default=None, max_length=80)


class RunCreateRequest(BaseModel):
    iso_label: str = Field(..., min_length=1, max_length=80)
    # 4.7 GB DVD-5 default — the engine's media-size ceiling for the
    # single-disc happy path.  Operators can drop to CD-700M or jump
    # to BD-25 by passing this explicitly.
    media_size_bytes: int = Field(default=4_700_000_000, gt=0)
    include_cve: bool = True
    include_compliance: bool = True
    # At least one target is required for the orchestrator to build a
    # meaningful collection plan.  The Pydantic validator below
    # enforces the non-empty invariant so we surface the 400 before
    # the row is even inserted, rather than letting the orchestrator
    # mark a target-less row as FAILED after the fact.
    targets: List[RunTargetSpec] = Field(default_factory=list)
    # Optional optical-burn device.  When set, the orchestrator
    # advances ISO_BUILT → BURNING by dispatching ``build_burn_plan``;
    # when NULL the run stops at ISO_BUILT (which then auto-advances
    # straight to COMPLETE).  Operators leave this NULL for the typical
    # "build an ISO file and download it" workflow.
    burn_device: Optional[str] = Field(default=None, max_length=200)


class RunResponse(BaseModel):
    id: str
    iso_label: str
    media_size_bytes: int
    include_cve: bool
    include_compliance: bool
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    cron_schedule: Optional[str] = None
    parent_run_id: Optional[str] = None
    created_at: Optional[str] = None
    worker_message_id: Optional[str] = None
    burn_device: Optional[str] = None
    # Actual on-disk size of the produced ISO(s), summed across discs.
    # None until the run has built something.  Distinct from
    # ``media_size_bytes`` (the configured per-disc capacity) so the UI can
    # show the REAL bundle size instead of the disc-size setting.
    iso_size_bytes: Optional[int] = None
    targets: List[RunTargetSpec] = Field(default_factory=list)


class ManifestResponse(BaseModel):
    id: str
    disc_index: int
    disc_count: int
    iso_path: str
    iso_sha256: str
    iso_size_bytes: int
    signer_fingerprint: str
    signature_algorithm: str
    format_version: int
    created_at: Optional[str] = None


def _snapshot_mirrors_for_run(
    db: Session,
    mirrors: List[models.MirrorRepository],
) -> dict:
    """Dispatch a snapshot for each of a run's target mirrors.

    Returns ``{mirror_id_str: placeholder_snapshot_row}`` so the
    caller can stamp each target row's ``source_snapshot_id`` to the
    placeholder snapshot id — that way the orchestrator can recognize
    the snapshot the run is waiting for even before the agent reports
    completion.

    Each mirror gets a fresh snapshot regardless of whether it had
    one moments ago: the goal is to bundle exactly the tree state at
    run-creation time, not some earlier state.

    Raises HTTPException(400) if the repository_mirroring engine
    isn't loaded — Option-B runs need it.  Caller is responsible for
    rolling back if any single dispatch fails (best-effort isn't OK
    here: a target missing its snapshot can never produce a bundle).
    """
    mirror_engine = module_loader.get_module("repository_mirroring_engine")
    if mirror_engine is None:
        raise HTTPException(
            status_code=400,
            detail=_(
                "Air-gap collection runs require the "
                "repository_mirroring_engine module to be loaded — "
                "the collector reads each target's bundle from a "
                "snapshot of its mirror tree."
            ),
        )
    settings_row = db.query(models.MirrorSettings).first()
    if settings_row is None or not settings_row.mirror_root_path:
        raise HTTPException(
            status_code=400,
            detail=_(
                "Global mirror settings missing or mirror_root_path "
                "not configured.  Configure mirror settings before "
                "creating a collection run."
            ),
        )

    # Late import so this module stays importable when
    # ``repository_mirroring`` isn't on the route registration list.
    from backend.api.repository_mirroring import (  # pylint: disable=import-outside-toplevel
        _config_from_row,
        _dispatch_plan,
    )

    placeholders: dict = {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for mirror in mirrors:
        snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3]
        plan = mirror_engine.build_mirror_snapshot_plan(
            _config_from_row(mirror),
            settings_row.mirror_root_path,
            snapshot_id,
        )
        msg_id = _dispatch_plan(
            plan,
            mirror.host_id,
            action="snapshot",
            mirror_id=str(mirror.id),
            timeout=600,
        )
        snap = models.MirrorSnapshot(
            repository_id=mirror.id,
            snapshot_id=snapshot_id,
            taken_at=now,
        )
        db.add(snap)
        db.flush()  # need snap.id immediately so we can FK target rows to it
        mirror.last_snapshot_at = now
        mirror.last_snapshot_status = "DISPATCHED"
        mirror.last_snapshot_error = None
        mirror.last_snapshot_message_id = msg_id
        placeholders[str(mirror.id)] = snap
    return placeholders


def _derive_target_meta(
    mirror: models.MirrorRepository,
) -> tuple[str, str]:
    """Return ``(distro, version)`` for a mirror.

    Pulled out of create_run so the same logic resolves both the
    insert-time stamping AND any later "re-derive after the operator
    edited the mirror" flow.  Requires the mirror to have
    ``known_version_id`` set — the catalog row's ``os_family`` is the
    canonical distro identifier; rolling our own apt-mirror url
    parsing here would just duplicate that registry.
    """
    if mirror.known_version_id is None:
        raise HTTPException(
            status_code=400,
            detail=_(
                "Mirror %r has no known_version_id set; "
                "Option-B collection runs need the mirror to be "
                "tied to a catalog version so distro / version can "
                "be derived.  Edit the mirror and pick a version "
                "from the dropdown."
            )
            % mirror.name,
        )
    known = mirror.known_version  # SQLAlchemy lazy-load via relationship
    if known is None:
        # known_version_id non-NULL but the row was deleted out from
        # under us — extremely rare.  Still a 400 since the operator
        # needs to fix the mirror config before we can proceed.
        raise HTTPException(
            status_code=400,
            detail=_(
                "Mirror %r references a catalog version that no "
                "longer exists.  Re-pick a version on the mirror."
            )
            % mirror.name,
        )
    distro = known.os_family
    # Pick the per-PM "version-shaped" field on the mirror itself
    # first (operators may override the catalog default at row
    # creation), falling back to the catalog defaults, finally to
    # the catalog's version_key.
    if mirror.package_manager == "apt":
        version = mirror.suite or known.default_suite or known.version_key
    elif mirror.package_manager == "dnf":
        version = mirror.release or known.default_release or known.version_key
    elif mirror.package_manager == "zypper":
        version = mirror.release or known.default_release or known.version_key
    elif mirror.package_manager == "pkg":
        version = mirror.release or known.default_release or known.version_key
    else:
        version = known.version_key
    return distro, version


def _serialize_target(target: models.AirgapCollectionTarget) -> RunTargetSpec:
    """Translate the persisted target row into the API response shape."""
    repos = (target.repos or "").split(",") if target.repos else []
    return RunTargetSpec(
        mirror_id=str(target.mirror_id) if target.mirror_id else "",
        distro=target.distro,
        version=target.version,
        repos=[r.strip() for r in repos if r.strip()],
        mirror_name=target.mirror.name if target.mirror else None,
        source_snapshot_id=(
            str(target.source_snapshot_id) if target.source_snapshot_id else None
        ),
    )


def _run_to_response(run: models.AirgapCollectionRun) -> RunResponse:
    """Convert a run row + its eagerly-loaded targets into RunResponse.

    Centralises the serialization so every endpoint produces the same
    shape — particularly important now that ``targets`` and
    ``burn_device`` join the existing scalar columns and the
    relationship lookup must happen under the session that's about
    to close.
    """
    payload = run.to_dict()
    payload["burn_device"] = run.burn_device
    payload["targets"] = [
        _serialize_target(t).model_dump() for t in (run.targets or [])
    ]
    # Real on-disk ISO size (sum across discs) so the UI shows the actual
    # bundle size, not the configured media-size setting.  None when no ISO
    # has been built yet, or if the files were cleaned off disk.
    try:
        discs = _list_run_discs(run.id)
        payload["iso_size_bytes"] = (
            sum(os.path.getsize(p) for p in discs) if discs else None
        )
    except OSError:
        payload["iso_size_bytes"] = None
    return RunResponse(**payload)


def _resolve_target_mirrors(
    db: Session, target_specs: List[RunTargetSpec]
) -> List[models.MirrorRepository]:
    """Load + validate every mirror the operator picked.

    Enforces the Option-B invariants:
      * Each mirror_id exists.
      * Each mirror is enabled (a disabled mirror's tree is
        unreliable — operator should re-enable + sync first).
      * All picked mirrors share a single host_id (the collection
        plan dispatches to one host, so cross-host targets aren't
        supported in v1 of Option-B).

    Returns the mirror rows in input order so the caller can pair
    them up with their target specs.
    """
    if not target_specs:
        raise HTTPException(
            status_code=400,
            detail=_("At least one target is required to create a collection run."),
        )
    mirrors: List[models.MirrorRepository] = []
    seen_hosts = set()
    for spec in target_specs:
        try:
            mid = uuid.UUID(spec.mirror_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=_("Invalid UUID for mirror_id: %s") % spec.mirror_id,
            ) from exc
        mirror = (
            db.query(models.MirrorRepository)
            .filter(models.MirrorRepository.id == mid)
            .first()
        )
        if mirror is None:
            raise HTTPException(
                status_code=400,
                detail=_("Mirror %s not found") % spec.mirror_id,
            )
        if not mirror.enabled:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Mirror %r is disabled; enable + sync it before "
                    "using it in a collection run."
                )
                % mirror.name,
            )
        seen_hosts.add(str(mirror.host_id))
        mirrors.append(mirror)
    if len(seen_hosts) > 1:
        raise HTTPException(
            status_code=400,
            detail=_(
                "All target mirrors must live on the same host "
                "(the collection plan dispatches to a single agent). "
                "Selected mirrors span %d hosts."
            )
            % len(seen_hosts),
        )
    return mirrors


@router.post("/runs", response_model=RunResponse)
async def create_run(
    request: RunCreateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Create a one-shot collection run (Option-B / snapshot-sourced).

    ``cron_schedule`` is left NULL — recurring runs go through
    ``airgap_collection_schedule.py``'s tick mechanism; this endpoint
    is strictly for ad-hoc UI-triggered runs.  The ``airgap_run_tick``
    background service picks the row up from ``status='QUEUED'`` and
    drives it through the lifecycle.

    Flow:

      1. Resolve every target's mirror, validate, derive (distro,
         version) from the mirror's known_version catalog row.
      2. Dispatch one snapshot per target mirror — these are the
         exact snapshots the bundle will rsync from.
      3. Insert AirgapCollectionTarget rows pointing at the mirror
         AND the placeholder snapshot row.
      4. Insert the AirgapCollectionRun row at status=QUEUED.

    The orchestrator polls QUEUED runs, waits for each target's
    snapshot's ``last_snapshot_message_id`` to clear, then dispatches
    a snapshot-sourced collection plan that rsyncs each snapshot dir
    into the staging tree.
    """
    _check_collector_module()
    if not request.targets:
        raise HTTPException(
            status_code=400,
            detail=_("At least one target is required to create a collection run."),
        )
    user = _get_user(db, current_user)

    # Resolve + validate before any side-effect — we want a clean 400
    # if anything's wrong, not a half-created run with a snapshot
    # dispatched to nowhere.
    mirrors = _resolve_target_mirrors(db, request.targets)
    target_meta = [_derive_target_meta(m) for m in mirrors]

    # Snapshot side-effect.  If any single dispatch raises we let it
    # bubble out as a 500 — caller will see the run wasn't created
    # and can retry.  Previously-dispatched snapshots in this loop
    # will still complete server-side; they just won't be tied to a
    # run, which is fine (operator can restore from them if desired).
    snapshot_placeholders = _snapshot_mirrors_for_run(db, mirrors)

    run = models.AirgapCollectionRun(
        iso_label=request.iso_label,
        media_size_bytes=request.media_size_bytes,
        include_cve=request.include_cve,
        include_compliance=request.include_compliance,
        burn_device=request.burn_device,
        status="QUEUED",
        cron_schedule=None,
        created_by=user.id,
    )
    db.add(run)
    db.flush()  # need run.id before inserting targets
    for spec, mirror, (distro, version) in zip(request.targets, mirrors, target_meta):
        placeholder = snapshot_placeholders.get(str(mirror.id))
        db.add(
            models.AirgapCollectionTarget(
                run_id=run.id,
                mirror_id=mirror.id,
                source_snapshot_id=placeholder.id if placeholder else None,
                distro=distro,
                version=version,
                # AirgapCollectionTarget stores ``repos`` as a CSV
                # column — the engine consumes that same shape via
                # ``target.repos.split(',')`` in the orchestrator.
                repos=",".join(spec.repos) if spec.repos else None,
            )
        )
    db.commit()
    db.refresh(run)
    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=str(run.id),
        entity_name=run.iso_label,
        description=(
            _(
                "Created one-shot air-gap collection run '%s' with "
                "%d target mirror(s); snapshots dispatched."
            )
            % (run.iso_label, len(mirrors))
        ),
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return _run_to_response(run)


@router.get("/runs", response_model=List[RunResponse])
async def list_runs(db: Session = Depends(get_db)):
    _check_collector_module()
    rows = (
        db.query(models.AirgapCollectionRun)
        .order_by(models.AirgapCollectionRun.created_at.desc())
        .all()
    )
    return [_run_to_response(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, db: Session = Depends(get_db)):
    _check_collector_module()
    rid = _parse_run_uuid(run_id)
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == rid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail=_(_ERR_RUN_NOT_FOUND))
    return _run_to_response(run)


# Where the orchestrator's build_iso_plan / multi-disc plan writes
# its output.  Mirrors the path baked into airgap_run_tick — both
# sides must agree or the download 410s.
_ISO_OUTPUT_DIR = "/var/lib/sysmanage/airgap-iso"


def _list_run_discs(run_id: uuid.UUID) -> List[str]:
    """Return absolute paths of every disc ISO on disk for a run.

    Single-disc runs produce ``<run_id>.iso``; multi-disc runs produce
    ``<run_id>-disc-1.iso``, ``<run_id>-disc-2.iso``, etc.  Returns the
    list sorted by disc index (single-disc first if both exist, which
    shouldn't happen but we don't enforce it).
    """
    single = os.path.join(_ISO_OUTPUT_DIR, f"{run_id}.iso")
    out: List[str] = []
    if os.path.isfile(single):
        out.append(single)
    idx = 1
    while True:
        disc = os.path.join(_ISO_OUTPUT_DIR, f"{run_id}-disc-{idx}.iso")
        if not os.path.isfile(disc):
            break
        out.append(disc)
        idx += 1
    return out


@router.get("/runs/{run_id}/discs")
async def list_run_discs(run_id: str, db: Session = Depends(get_db)):
    """List the disc ISOs available for a run (multi-disc runs only).

    Used by the UI to render a per-disc download list when
    ``disc_count > 1``.  Returns ``[{disc_index, filename, size_bytes}]``;
    empty list if the run hasn't finished or single-disc.
    """
    _check_collector_module()
    rid = _parse_run_uuid(run_id)
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == rid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail=_(_ERR_RUN_NOT_FOUND))
    discs = _list_run_discs(rid)
    result = []
    for path in discs:
        name = os.path.basename(path)
        # Pull the disc index out of the suffix; single-disc files
        # report disc_index=1 for UI uniformity.
        if "-disc-" in name:
            try:
                index = int(name.rsplit("-disc-", 1)[1].split(".", 1)[0])
            except ValueError:
                index = 0
        else:
            index = 1
        result.append(
            {
                "disc_index": index,
                "filename": name,
                "size_bytes": os.path.getsize(path),
            }
        )
    return result


def _get_run_or_404(db: Session, rid: uuid.UUID) -> models.AirgapCollectionRun:
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == rid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail=_(_ERR_RUN_NOT_FOUND))
    return run


def _assert_iso_ready(run: models.AirgapCollectionRun) -> List[str]:
    """409 if the run hasn't produced an ISO yet, 410 if the file(s) were
    cleaned off disk; otherwise return the list of available disc paths."""
    if run.status not in ("ISO_BUILT", "BURNING", "COMPLETE"):
        raise HTTPException(
            status_code=409,
            detail=_(
                "ISO is not ready for download yet (status: %s). "
                "Wait until the run reaches ISO_BUILT."
            )
            % run.status,
        )
    available = _list_run_discs(run.id)
    if not available:
        raise HTTPException(
            status_code=410,
            detail=_(
                "ISO file no longer on disk; the staging volume may "
                "have been cleaned. Re-run the collection to rebuild."
            ),
        )
    return available


def _assert_within_iso_dir(path: str) -> str:
    """Reject any ISO path that resolves outside ``_ISO_OUTPUT_DIR``.

    Defence in depth: the served paths come from a glob of the ISO dir or a
    server-written DB column, so they're already contained — but this realpath
    check guarantees a route-param/DB-derived path can never escape, and is the
    form the path-traversal scanners recognise."""
    root = os.path.realpath(_ISO_OUTPUT_DIR)
    resolved = os.path.realpath(path)
    if not resolved.startswith(root + os.sep):
        raise HTTPException(status_code=404, detail=_("ISO file not found."))
    return resolved


def _iso_file_response(
    run: models.AirgapCollectionRun, disc: Optional[int]
) -> FileResponse:
    """Resolve the on-disk ISO for ``run`` (+ optional ``disc``) and return
    a streaming FileResponse.  Shared by the header-authed ``/iso`` route
    and the token-authed ``/iso-download`` route.  FileResponse streams the
    file in chunks, so a multi-GB ISO never buffers in memory."""
    available = _assert_iso_ready(run)
    if disc is None or disc == 1:
        chosen = available[0]
    else:
        target = os.path.join(_ISO_OUTPUT_DIR, f"{run.id}-disc-{disc}.iso")
        if target not in available:
            raise HTTPException(
                status_code=404,
                detail=_("Disc %d not found for this run.  Available discs: %s")
                % (disc, ", ".join(os.path.basename(p) for p in available)),
            )
        chosen = target
    is_multidisc = len(available) > 1 or "-disc-" in os.path.basename(chosen)
    if is_multidisc:
        name = os.path.basename(chosen)
        try:
            idx = int(name.rsplit("-disc-", 1)[1].split(".", 1)[0])
            friendly = f"{run.iso_label}-disc-{idx}.iso"
        except ValueError:
            friendly = f"{run.iso_label}-{run.id}.iso"
    else:
        friendly = f"{run.iso_label}-{run.id}.iso"
    # Path containment is enforced by _assert_within_iso_dir (realpath +
    # startswith); the served path is always a glob result under the ISO dir.
    chosen = _assert_within_iso_dir(chosen)
    return FileResponse(
        # nosemgrep: python.fastapi.file.tainted-path-traversal-fastapi.tainted-path-traversal-fastapi
        chosen,
        media_type="application/octet-stream",
        filename=friendly,
    )


@router.get("/runs/{run_id}/iso")
async def download_run_iso(
    run_id: str,
    disc: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Stream an ISO file produced by a completed collection run
    (header-authenticated).  Kept for API clients that can send the
    Authorization header; the UI uses the token-authed ``/iso-download``
    route below for large native downloads.
    """
    _check_collector_module()
    rid = _parse_run_uuid(run_id)
    run = _get_run_or_404(db, rid)
    return _iso_file_response(run, disc)


@router.post("/runs/{run_id}/iso-token")
async def create_iso_download_token(
    run_id: str,
    current_user: str = Depends(get_current_user),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    """Mint a short-lived, single-run token for a native streaming ISO
    download.  The browser can't put the session JWT in the Authorization
    header when it follows a plain download link, and buffering a multi-GB
    ISO through fetch() to add the header OOMs the tab — so the UI calls
    this (authenticated), then points the browser at GET /iso-download with
    the returned token, which streams straight to disk.
    """
    _check_collector_module()
    rid = _parse_run_uuid(run_id)
    run = _get_run_or_404(db, rid)
    _assert_iso_ready(run)  # don't hand out a token unless it's downloadable
    return {"token": sign_airgap_download_token(str(rid)), "expires_in": 300}


@download_router.get("/runs/{run_id}/iso-download")
async def download_run_iso_streamed(
    run_id: str,
    token: str,
    disc: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Token-authenticated streaming ISO download.

    NOT on the header-authed router: the browser navigates here directly
    (so it can't carry the Authorization header), authenticating with the
    short-lived, single-run token minted by POST /runs/{id}/iso-token.  The
    response streams straight to disk — no in-memory buffering — so a
    multi-GB bundle downloads without OOMing the browser or the backend.
    """
    rid = _parse_run_uuid(run_id)
    if not decode_airgap_download_token(token, str(rid)):
        raise HTTPException(
            status_code=403,
            detail=_("Invalid or expired download token."),
        )
    run = _get_run_or_404(db, rid)
    return _iso_file_response(run, disc)


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    _check_collector_module()
    user = _get_user(db, current_user)
    rid = _parse_run_uuid(run_id)
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == rid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail=_(_ERR_RUN_NOT_FOUND))
    label = run.iso_label
    # Cascade handles targets + manifests rows; the ISO file on disk
    # is the engine's responsibility to clean up out of band.
    db.delete(run)
    db.commit()
    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.SETTING,
        entity_id=str(rid),
        entity_name=label,
        description=_("Deleted air-gap collection run '%s'") % label,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return None


@router.get("/runs/{run_id}/manifests", response_model=List[ManifestResponse])
async def list_manifests(run_id: str, db: Session = Depends(get_db)):
    _check_collector_module()
    rid = _parse_run_uuid(run_id)
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == rid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail=_(_ERR_RUN_NOT_FOUND))
    manifests = (
        db.query(models.AirgapMediaManifest)
        .filter(models.AirgapMediaManifest.run_id == rid)
        .order_by(models.AirgapMediaManifest.disc_index)
        .all()
    )
    return [
        ManifestResponse(
            id=str(m.id),
            disc_index=m.disc_index,
            disc_count=m.disc_count,
            iso_path=m.iso_path,
            iso_sha256=m.iso_sha256,
            iso_size_bytes=m.iso_size_bytes,
            signer_fingerprint=m.signer_fingerprint,
            signature_algorithm=m.signature_algorithm,
            format_version=m.format_version,
            created_at=m.created_at.isoformat() if m.created_at else None,
        )
        for m in manifests
    ]


@router.get("/manifests/{manifest_id}/download")
async def download_manifest_iso(
    manifest_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),  # noqa: ARG001
):
    """Stream the signed ISO referenced by ``manifest.iso_path``.

    The endpoint is wired here (rather than on the manifest's own
    sub-resource) so it cleanly maps to "one ISO per manifest row" —
    multi-disc runs produce N manifest rows and the UI can hit this
    endpoint once per row to pull each disc.
    """
    _check_collector_module()
    mid = _parse_manifest_uuid(manifest_id)
    manifest = (
        db.query(models.AirgapMediaManifest)
        .filter(models.AirgapMediaManifest.id == mid)
        .first()
    )
    if not manifest:
        raise HTTPException(status_code=404, detail=_(_ERR_MANIFEST_NOT_FOUND))
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == manifest.run_id)
        .first()
    )
    if run is None or run.status != "COMPLETE":
        raise HTTPException(
            status_code=409,
            detail=_("Run is not COMPLETE yet (status: %s)")
            % (run.status if run else "UNKNOWN"),
        )
    if not manifest.iso_path or not os.path.isfile(manifest.iso_path):
        raise HTTPException(
            status_code=410,
            detail=_("ISO file is no longer on disk: %s") % (manifest.iso_path or ""),
        )
    # Path containment is enforced by _assert_within_iso_dir (realpath +
    # startswith); iso_path is a server-written column always under the ISO dir.
    safe_iso_path = _assert_within_iso_dir(manifest.iso_path)
    return FileResponse(
        # nosemgrep: python.fastapi.file.tainted-path-traversal-fastapi.tainted-path-traversal-fastapi
        safe_iso_path,
        media_type="application/octet-stream",
        filename=os.path.basename(safe_iso_path),
    )
