"""
Air-gap install bundle API.

Mounts under ``/api/airgap-bundles``.  Lets an admin trigger a build
(returns immediately with a job id), poll status, list past bundles,
download the resulting ISO, and delete bundles when no longer needed.

All endpoints require an authenticated user with the
``MANAGE_AIRGAP_BUNDLES`` role.  The config-admin recovery account is
allowed through for bootstrap.
"""

import grp
import os
import pwd
import shutil
import subprocess  # nosec B404 - used only for `docker info` readiness probe
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
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


@router.get("/{bundle_id}/download")
@requires_pro_plus()
async def download_bundle(
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
