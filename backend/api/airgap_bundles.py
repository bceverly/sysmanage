"""
Air-gap install bundle API.

Mounts under ``/api/airgap-bundles``.  Lets an admin trigger a build
(returns immediately with a job id), poll status, list past bundles,
download the resulting ISO, and delete bundles when no longer needed.

All endpoints require an authenticated user with the
``MANAGE_AIRGAP_BUNDLES`` role.  The config-admin recovery account is
allowed through for bootstrap.
"""

import os
import shutil
import subprocess  # nosec B404 - used only for `docker info` readiness probe
import uuid
from typing import List, Optional

# grp/pwd are POSIX-only stdlib modules; on Windows the airgap bundle
# builder doesn't run (Docker-per-distro-Linux can only be driven from
# a Linux host) but the module still has to import cleanly so the
# rest of the backend works on Windows CI.
try:
    import grp
    import pwd
except ImportError:  # Windows
    grp = None  # type: ignore[assignment]
    pwd = None  # type: ignore[assignment]

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.auth.auth_handler import (
    decode_airgap_bundle_token,
    sign_airgap_bundle_token,
)
from backend.config import config
from backend.i18n import _
from backend.licensing.feature_gate import requires_pro_plus
from backend.persistence import db, models
from backend.services import airgap_bundle_builder
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.airgap_bundles")

router = APIRouter(
    prefix="/airgap-bundles",
    tags=["airgap-bundles"],
    dependencies=[Depends(JWTBearer())],
)

# Bundle ISOs are multi-GB; a browser can't put the session JWT on a
# plain download link and buffering the whole file through fetch() to
# add the header OOMs the tab.  So this router carries NO blanket
# JWTBearer — its one route is authorised by a short-lived single-bundle
# token minted by the authenticated POST /{id}/download-token below.
download_router = APIRouter(
    prefix="/airgap-bundles",
    tags=["airgap-bundles"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class BundleCreateRequest(BaseModel):
    product: str  # "server" or "agent"


class BundleResponse(BaseModel):
    id: str
    product: str
    status: str
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    size_bytes: Optional[int]
    error_message: Optional[str]
    version: Optional[str]


class DockerStatusResponse(BaseModel):
    installed: bool  # docker binary on PATH
    running: bool  # `docker info` succeeds
    version: Optional[str]  # parsed from `docker --version`
    user_in_group: bool  # current process user is in the docker group
    process_user: str  # the OS user the API is running as
    error: Optional[str]  # short human-readable diagnostic when not ready
    permission_denied: bool  # daemon reachable on socket but we can't read it


class ResourceStatusResponse(BaseModel):
    ram_total_mb: Optional[int]
    ram_available_mb: Optional[int]  # real RAM a new process can take now
    swap_total_mb: Optional[int]
    swap_free_mb: Optional[int]
    available_mb: Optional[int]  # ram_available + swap_free
    disk_free_gb: Optional[float]  # min free across bundle dir + staging
    disk_total_gb: Optional[float]
    min_available_mb: int  # threshold below which a build is blocked
    min_disk_gb: int
    severity: str  # "ok" | "warn" | "insufficient"
    sufficient: bool  # False => build is blocked
    reason: Optional[str]  # human-readable detail when not "ok"


# Resource thresholds for a Docker-driven multi-platform bundle build.
# The dominant costs are per-distro ``pip wheel`` compilation (cryptography,
# cffi, …) — each wants ~1 GB — plus a multi-GB staging tree and the ISO.
# A host that can't cover these silently OOM-kills the per-distro builds
# and ships a hollow ISO, so we gate the build on them up front.
_MIN_BUILD_AVAIL_MB = 2048  # RAM + free swap below this -> block
_SOFT_BUILD_RAM_MB = 1024  # real RAM available below this -> warn (swap-heavy)
_MIN_BUILD_DISK_GB = 5  # free disk below this -> block
_SOFT_BUILD_DISK_GB = 10  # free disk below this -> warn

# Where buildAirGapBundle.sh stages the build (its STAGING_DIR default).
# We only ``stat`` its free space here — we never create a file in it — so
# the bandit hardcoded-tmp warning does not apply.
_STAGING_PARENT = "/var/tmp"  # nosec B108 - read-only disk_usage probe, not a temp file


def _read_meminfo_mb():
    """(mem_total, mem_available, swap_total, swap_free) in MB, or None
    on non-Linux / unreadable ``/proc/meminfo``."""
    try:
        vals = {}
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split(":")
                if len(parts) != 2:
                    continue
                num = parts[1].strip().split()
                if num and num[0].isdigit():
                    vals[parts[0].strip()] = int(num[0]) // 1024  # kB -> MB
        return (
            vals.get("MemTotal", 0),
            vals.get("MemAvailable", 0),
            vals.get("SwapTotal", 0),
            vals.get("SwapFree", 0),
        )
    except OSError:
        return None


def _disk_free_bytes(path: str) -> Optional[int]:
    """Free bytes on the filesystem holding ``path``.  Walks up to the
    nearest existing ancestor so a not-yet-created bundle dir doesn't
    raise."""
    p = path
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    if not p or not os.path.exists(p):
        return None
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


def _check_build_resources() -> dict:
    """Assess whether the host can run a Docker bundle build.  Shape
    matches ``ResourceStatusResponse``."""
    # Disk: the build stages under /var/tmp and writes the ISO to
    # BUNDLE_DIR — both need room, possibly on different filesystems.
    frees = [
        b
        for b in (
            _disk_free_bytes(str(airgap_bundle_builder.BUNDLE_DIR)),
            _disk_free_bytes(_STAGING_PARENT),
        )
        if b is not None
    ]
    disk_free_bytes = min(frees) if frees else None
    disk_free_gb = (
        round(disk_free_bytes / (1024**3), 1) if disk_free_bytes is not None else None
    )
    try:
        disk_total_gb = round(shutil.disk_usage(_STAGING_PARENT).total / (1024**3), 1)
    except OSError:
        disk_total_gb = None

    mem = _read_meminfo_mb()
    if mem is None:
        # Non-Linux / unreadable.  docker-status already blocks non-Linux
        # hosts, so don't double-block here — report unknown but allow.
        return {
            "ram_total_mb": None,
            "ram_available_mb": None,
            "swap_total_mb": None,
            "swap_free_mb": None,
            "available_mb": None,
            "disk_free_gb": disk_free_gb,
            "disk_total_gb": disk_total_gb,
            "min_available_mb": _MIN_BUILD_AVAIL_MB,
            "min_disk_gb": _MIN_BUILD_DISK_GB,
            "severity": "ok",
            "sufficient": True,
            "reason": None,
        }

    mem_total, mem_avail, swap_total, swap_free = mem
    available_mb = mem_avail + swap_free
    reasons = []
    severity = "ok"

    if available_mb < _MIN_BUILD_AVAIL_MB:
        severity = "insufficient"
        reasons.append(
            f"only {available_mb} MB of RAM+swap free; need ≥ {_MIN_BUILD_AVAIL_MB} MB "
            f"(add swap or grow the VM)"
        )
    if disk_free_gb is not None and disk_free_gb < _MIN_BUILD_DISK_GB:
        severity = "insufficient"
        reasons.append(
            f"only {disk_free_gb} GB free disk; need ≥ {_MIN_BUILD_DISK_GB} GB"
        )

    if severity != "insufficient":
        if mem_avail < _SOFT_BUILD_RAM_MB:
            severity = "warn"
            reasons.append(
                f"only {mem_avail} MB real RAM free — the build will lean on swap "
                f"and run slowly"
            )
        if disk_free_gb is not None and disk_free_gb < _SOFT_BUILD_DISK_GB:
            severity = "warn"
            reasons.append(
                f"only {disk_free_gb} GB free disk — a full build can use several GB"
            )

    return {
        "ram_total_mb": mem_total,
        "ram_available_mb": mem_avail,
        "swap_total_mb": swap_total,
        "swap_free_mb": swap_free,
        "available_mb": available_mb,
        "disk_free_gb": disk_free_gb,
        "disk_total_gb": disk_total_gb,
        "min_available_mb": _MIN_BUILD_AVAIL_MB,
        "min_disk_gb": _MIN_BUILD_DISK_GB,
        "severity": severity,
        "sufficient": severity != "insufficient",
        "reason": "; ".join(reasons) if reasons else None,
    }


def _row_to_response(row: models.AirGapBundle) -> BundleResponse:
    return BundleResponse(
        id=str(row.id),
        product=row.product,
        status=row.status,
        created_at=row.created_at.isoformat() + "Z" if row.created_at else None,
        started_at=row.started_at.isoformat() + "Z" if row.started_at else None,
        completed_at=(row.completed_at.isoformat() + "Z" if row.completed_at else None),
        size_bytes=row.size_bytes,
        error_message=row.error_message,
        version=row.version,
    )


# ---------------------------------------------------------------------------
# Authorization helper
# ---------------------------------------------------------------------------


def _resolve_caller_user_id(current_user: str) -> Optional[uuid.UUID]:
    """Return the calling user's User.id, or None for the config-admin.

    Allows the config-admin recovery account to trigger bundles (the
    initial bootstrap path) without needing a DB row.  Real users get
    their id stamped on the audit trail.
    """
    the_config = config.get_config()
    admin_userid = the_config.get("security", {}).get("admin_userid")
    if admin_userid and current_user == admin_userid:
        return None
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        return user.id if user else None


# ---------------------------------------------------------------------------
# GET /airgap-bundles/docker-status — pre-flight check before kicking
# off a build (the Settings UI uses this to surface a "Docker isn't
# ready, here's how to install it" banner instead of letting the
# build subprocess fail silently with a cryptic log file).
# ---------------------------------------------------------------------------


@router.get("/docker-status", response_model=DockerStatusResponse)
@requires_pro_plus()
async def docker_status(
    current_user: str = Depends(get_current_user),  # noqa: ARG001
) -> DockerStatusResponse:
    # The bundle builder only works from a Linux host (Docker-per-
    # distro-Linux containers can't be driven from Windows).  Return
    # a clean "not supported here" response on Windows rather than
    # tripping over pwd/grp being unavailable.
    if pwd is None or grp is None:
        return DockerStatusResponse(
            installed=False,
            running=False,
            version=None,
            user_in_group=False,
            process_user="",
            error="Air-gap bundle builder is only supported on Linux build hosts",
            permission_denied=False,
        )

    # Identify the OS user this API process is running as — that's
    # the user that needs docker socket access, since the build
    # subprocess inherits the same uid/gid set.  In a packaged
    # install it's the 'sysmanage' system user; in dev it's whoever
    # ran `make start`.
    try:
        process_user = pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:
        process_user = ""

    docker_path = shutil.which("docker")
    if not docker_path:
        return DockerStatusResponse(
            installed=False,
            running=False,
            version=None,
            user_in_group=False,
            process_user=process_user,
            error="docker binary not found on PATH",
            permission_denied=False,
        )

    version: Optional[str] = None
    try:
        proc = subprocess.run(  # nosec B603 - fixed args, no user input
            [docker_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            version = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass

    running = False
    error: Optional[str] = None
    permission_denied = False
    try:
        proc = subprocess.run(  # nosec B603 - fixed args, no user input
            [docker_path, "info"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        running = proc.returncode == 0
        if not running:
            # Trim long output to a single useful line.
            stderr_line = (proc.stderr or "").strip().splitlines()
            error = stderr_line[0] if stderr_line else "docker info exited non-zero"
            # Differentiate "daemon down" from "daemon up but I can't
            # read the socket" — the latter is a group-membership
            # problem and needs a very different remediation.
            if error and "permission denied" in error.lower():
                permission_denied = True
    except (OSError, subprocess.SubprocessError) as exc:
        error = str(exc)

    user_in_group = False
    try:
        docker_group = grp.getgrnam("docker")
        # Check the *current process user* — that's who actually
        # spawns the build subprocess.  In a packaged install this is
        # the 'sysmanage' system user; in dev it's whoever started
        # `make run`.  Hardcoding 'sysmanage' would mis-flag dev hosts.
        try:
            current_username = pwd.getpwuid(os.geteuid()).pw_name
        except KeyError:
            current_username = ""
        # Either named-membership or the user's primary GID matches.
        user_in_group = (
            current_username in docker_group.gr_mem
            or docker_group.gr_gid in os.getgroups()
        )
    except KeyError:
        # No 'docker' group at all means docker package was never
        # installed via the system package manager.
        pass

    return DockerStatusResponse(
        installed=True,
        running=running,
        version=version,
        user_in_group=user_in_group,
        process_user=process_user,
        error=error,
        permission_denied=permission_denied,
    )


# ---------------------------------------------------------------------------
# GET /airgap-bundles/resource-status — RAM / swap / disk pre-flight.
# The Settings UI uses this to disable the Build buttons (and show a
# banner) when the host can't take a build, rather than letting the
# per-distro Docker builds get OOM-killed and silently ship a hollow ISO.
# ---------------------------------------------------------------------------


@router.get("/resource-status", response_model=ResourceStatusResponse)
@requires_pro_plus()
async def resource_status(
    current_user: str = Depends(get_current_user),  # noqa: ARG001
) -> ResourceStatusResponse:
    return ResourceStatusResponse(**_check_build_resources())


# ---------------------------------------------------------------------------
# POST /airgap-bundles — start a build
# ---------------------------------------------------------------------------


@router.post("", response_model=BundleResponse, status_code=202)
@requires_pro_plus()
async def create_bundle(
    req: BundleCreateRequest, current_user: str = Depends(get_current_user)
) -> BundleResponse:
    if req.product not in models.BUNDLE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=_("product must be one of: ") + ", ".join(models.BUNDLE_PRODUCTS),
        )

    # Resource gate.  The server/agent builds run Docker per distro and
    # compile wheels; refuse to start when the host can't take it — a
    # too-small host OOM-kills the per-distro builds and ships a hollow
    # ISO.  Pro+ overlay bundles are a lightweight file copy and skip
    # this gate.  Enforced server-side so it can't be bypassed by a
    # stale UI.
    if req.product in ("server", "agent"):
        res = _check_build_resources()
        if not res["sufficient"]:
            raise HTTPException(
                status_code=409,
                detail=_("Insufficient host resources to build a bundle: ")
                + (res["reason"] or ""),
            )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        row = models.AirGapBundle(
            product=req.product,
            status=models.BUNDLE_STATUS_QUEUED,
            created_by_user_id=_resolve_caller_user_id(current_user),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        bundle_id = row.id
        response = _row_to_response(row)

    airgap_bundle_builder.start_build(bundle_id, req.product)
    logger.info(
        "airgap_bundle %s queued (product=%s, by=%s)",
        bundle_id,
        req.product,
        current_user,
    )
    return response


# ---------------------------------------------------------------------------
# GET /airgap-bundles — list (newest first)
# ---------------------------------------------------------------------------


@router.get("", response_model=List[BundleResponse])
@requires_pro_plus()
async def list_bundles(
    current_user: str = Depends(get_current_user),  # noqa: ARG001
) -> List[BundleResponse]:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        rows = (
            session.query(models.AirGapBundle)
            .order_by(models.AirGapBundle.created_at.desc())
            .all()
        )
        return [_row_to_response(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /airgap-bundles/{id} — one bundle's status
# ---------------------------------------------------------------------------


@router.get("/{bundle_id}", response_model=BundleResponse)
@requires_pro_plus()
async def get_bundle(
    bundle_id: uuid.UUID,
    current_user: str = Depends(get_current_user),  # noqa: ARG001
) -> BundleResponse:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        row = (
            session.query(models.AirGapBundle)
            .filter(models.AirGapBundle.id == bundle_id)
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail=_("Bundle not found"))
        return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /airgap-bundles/{id}/download — stream the ISO
# ---------------------------------------------------------------------------


def _bundle_file_response(bundle_id: uuid.UUID) -> FileResponse:
    """Resolve a READY bundle to a streaming FileResponse, or raise.

    FileResponse streams the file off disk in chunks — it never loads
    the multi-GB ISO into memory — so this is safe for any size.  Shared
    by the header-authed ``/download`` route and the token-authed
    ``/download-stream`` route.
    """
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        row = (
            session.query(models.AirGapBundle)
            .filter(models.AirGapBundle.id == bundle_id)
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail=_("Bundle not found"))
        if row.status != models.BUNDLE_STATUS_READY:
            raise HTTPException(
                status_code=409,
                detail=_("Bundle is not ready yet (status: %s)") % row.status,
            )
        if not row.file_path or not os.path.isfile(row.file_path):
            raise HTTPException(
                status_code=410, detail=_("Bundle file is no longer on disk")
            )
        return FileResponse(
            row.file_path,
            media_type="application/octet-stream",
            filename=os.path.basename(row.file_path),
        )


@router.get("/{bundle_id}/download")
@requires_pro_plus()
async def download_bundle(
    bundle_id: uuid.UUID,
    current_user: str = Depends(get_current_user),  # noqa: ARG001
):
    """Header-authed streaming download (kept for API clients/scripts)."""
    return _bundle_file_response(bundle_id)


@router.post("/{bundle_id}/download-token")
@requires_pro_plus()
async def mint_bundle_download_token(
    bundle_id: uuid.UUID,
    current_user: str = Depends(get_current_user),  # noqa: ARG001
):
    """Mint a short-lived token authorising one streaming bundle download.

    The UI POSTs here (authenticated), then points the browser straight
    at GET /{id}/download-stream?token=… so the browser streams the
    multi-GB ISO to disk without buffering it in a fetch()/Blob.
    """
    # Validate the bundle is real + ready before handing out a token.
    _bundle_file_response(bundle_id)
    return {"token": sign_airgap_bundle_token(str(bundle_id)), "expires_in": 300}


@download_router.get("/{bundle_id}/download-stream")
@requires_pro_plus()
async def download_bundle_stream(bundle_id: uuid.UUID, token: str = ""):
    """Token-authed streaming bundle download (no Authorization header).

    Authorised by the short-lived single-bundle token from POST
    /{id}/download-token.  The browser navigates here directly so the
    download streams to disk.
    """
    if not decode_airgap_bundle_token(token, str(bundle_id)):
        raise HTTPException(
            status_code=401, detail=_("Invalid or expired download token")
        )
    return _bundle_file_response(bundle_id)


# ---------------------------------------------------------------------------
# DELETE /airgap-bundles/{id} — remove file + row
# ---------------------------------------------------------------------------


@router.delete("/{bundle_id}", status_code=204)
@requires_pro_plus()
async def delete_bundle(
    bundle_id: uuid.UUID,
    current_user: str = Depends(get_current_user),  # noqa: ARG001
):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        row = (
            session.query(models.AirGapBundle)
            .filter(models.AirGapBundle.id == bundle_id)
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail=_("Bundle not found"))
        # Remove on-disk artifact + log (best effort).
        for path_attr in ("file_path", "log_path"):
            p = getattr(row, path_attr, None)
            if p and os.path.isfile(p):
                try:
                    os.unlink(p)
                except OSError as exc:
                    logger.warning("couldn't unlink %s: %s", p, exc)
        session.delete(row)
        session.commit()
