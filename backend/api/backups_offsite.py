# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The off-site cloud copy: S3 Glacier Deep Archive (ROADMAP 27.3).

Setting up and running the copy (create, change, "Run now", a new key) is
Professional+ and answers 402 without the engine.  Everything that gets the
data back works in every edition, also after a lapse: reading the copy and
what is in the bucket, checking the credentials, turning the copy off,
restoring, and the sealed key export.

Viewing needs a signed-in user; changing, Manage Backups; a restore, Restore
Files; the key export, both Manage Backups and Restore Files.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _require
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_breakglass as breakglass
from backend.services import backup_jobs as jobs
from backend.services import backup_offsite as offsite
from backend.services import backup_offsite_export as export
from backend.services import backup_offsite_runs as runs
from backend.services.audit_service import EntityType
from backend.services.backup_escrow import escrow_target

router = APIRouter(dependencies=[Depends(JWTBearer())])


class CopyBody(BaseModel):
    target_id: Optional[str] = Field(default=None, max_length=64)
    bucket: Optional[str] = Field(default=None, max_length=63)
    region: Optional[str] = Field(default=None, max_length=32)
    endpoint: Optional[str] = Field(default=None, max_length=255)
    prefix: Optional[str] = Field(default=None, max_length=200)
    storage_class: Optional[str] = Field(default=None, max_length=16)
    object_lock: Optional[bool] = None
    enabled: Optional[bool] = None
    access_key: Optional[str] = Field(default=None, max_length=128)
    secret_key: Optional[str] = Field(default=None, max_length=256)
    settings: Optional[Dict[str, Any]] = None


class RestoreBody(BaseModel):
    dataset: str = Field(min_length=1, max_length=255)
    snapshot: str = Field(min_length=1, max_length=64)
    tier: str = Field(default="Bulk", max_length=16)
    target_dataset: Optional[str] = Field(default=None, max_length=255)
    host_id: Optional[str] = Field(default=None, max_length=64)


class ExportBody(BaseModel):
    recipient_key: Optional[str] = Field(
        default=None, max_length=breakglass.MAX_RECIPIENT_BYTES
    )
    reason: str = Field(min_length=1, max_length=breakglass.MAX_REASON_CHARS * 2)


def _refused(error: offsite.OffsiteRefused) -> HTTPException:
    return HTTPException(status_code=error.status, detail=str(error))


def _who(current_user) -> str:
    return getattr(current_user, "userid", None) or "unknown"


def _log(db, current_user, copy, description, details=None):
    _audit(db, current_user, EntityType.SETTING, copy.id, f"off-site copy {copy.bucket}",
           description, details or {})  # fmt: skip


@router.get("/backups/offsite")
def list_copies(db: Session = Depends(get_tenant_db),
                current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    module = offsite.engine()
    return {
        "available": not offsite.airgapped(),
        "licensed": module is not None,
        "defaults": module.offsite_defaults() if module is not None else None,
        "copies": [offsite.view(db, c) for c in offsite.copies(db)],
        "targets": [{"id": str(t.id), "name": t.name, "storage_path": t.storage_path,
                     "has_storage_host": t.storage_host_id is not None}
                    for t in jobs.targets(db)],
    }  # fmt: skip


@router.post("/backups/offsite")
def create_copy(body: CopyBody, db: Session = Depends(get_tenant_db),
                current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    try:
        copy = offsite.create(
            db, body.model_dump(exclude_none=True), _who(current_user)
        )
    except offsite.OffsiteRefused as error:
        raise _refused(error) from error
    _log(db, current_user, copy, "Off-site cloud copy set up",
         {"bucket": copy.bucket, "region": copy.region, "prefix": copy.prefix})  # fmt: skip
    db.commit()
    return offsite.view(db, copy)


@router.put("/backups/offsite/{copy_id}")
def update_copy(copy_id: str, body: CopyBody, db: Session = Depends(get_tenant_db),
                current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    data = body.model_dump(exclude_unset=True)
    data.pop("target_id", None)
    try:
        copy = offsite.update(db, copy_id, data, _who(current_user))
    except offsite.OffsiteRefused as error:
        raise _refused(error) from error
    changed = sorted(k for k in data if k not in ("access_key", "secret_key"))
    if data.get("access_key"):
        changed.append("credentials")
    _log(db, current_user, copy, "Off-site cloud copy changed", {"fields": changed})
    db.commit()
    return offsite.view(db, copy)


def _queued(db, current_user, copy_id, start, description) -> Dict[str, Any]:
    try:
        run = start()
    except offsite.OffsiteRefused as error:
        raise _refused(error) from error
    _log(
        db,
        current_user,
        offsite.get_copy(db, copy_id),
        description,
        {"run_id": str(run.id)},
    )
    db.commit()
    return runs.run_view(run)


@router.post("/backups/offsite/{copy_id}/check")
def check_copy(copy_id: str, db: Session = Depends(get_tenant_db),
               current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    return _queued(db, current_user, copy_id,
                   lambda: runs.queue_check(db, copy_id, _who(current_user)),
                   "Off-site cloud copy check started")  # fmt: skip


@router.post("/backups/offsite/{copy_id}/run")
def run_copy(copy_id: str, db: Session = Depends(get_tenant_db),
             current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    return _queued(db, current_user, copy_id,
                   lambda: runs.queue_upload(db, copy_id, _who(current_user)),
                   "Off-site cloud copy upload started")  # fmt: skip


@router.post("/backups/offsite/{copy_id}/rotate-key")
def rotate_key(copy_id: str, db: Session = Depends(get_tenant_db),
               current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    try:
        kid = offsite.rotate_key(db, copy_id, _who(current_user))
    except offsite.OffsiteRefused as error:
        raise _refused(error) from error
    copy = offsite.get_copy(db, copy_id)
    _log(db, current_user, copy, "Off-site cloud copy key rotated", {"key_id": kid})
    db.commit()
    return offsite.view(db, copy)


@router.get("/backups/offsite/{copy_id}/setup")
def setup_help(copy_id: str, db: Session = Depends(get_tenant_db),
               current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    try:
        copy = offsite.get_copy(db, copy_id)
    except offsite.OffsiteRefused as error:
        raise _refused(error) from error
    found = offsite.setup_help(db, copy)
    if found is None:
        raise HTTPException(
            status_code=402, detail=_("The setup guide needs Professional+")
        )
    return found


@router.get("/backups/offsite/{copy_id}/runs")
def list_runs(copy_id: str, db: Session = Depends(get_tenant_db),
              current_user=Depends(require_authenticated_user)) -> List[Dict[str, Any]]:  # fmt: skip
    return runs.runs(db, copy_id)


@router.get("/backups/offsite/{copy_id}/restore-points")
def restore_points(copy_id: str, db: Session = Depends(get_tenant_db),
                   current_user=Depends(require_authenticated_user)) -> List[Dict[str, Any]]:  # fmt: skip
    return runs.restore_points(db, copy_id)


@router.post("/backups/offsite/{copy_id}/restore/estimate")
def restore_estimate(copy_id: str, body: RestoreBody, db: Session = Depends(get_tenant_db),
                     current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    try:
        links = runs.chain(db, copy_id, body.dataset, body.snapshot)
    except offsite.OffsiteRefused as error:
        raise _refused(error) from error
    return dict(runs.estimate(links, body.tier), streams=len(links))


@router.post("/backups/offsite/{copy_id}/restore")
def restore(copy_id: str, body: RestoreBody, db: Session = Depends(get_tenant_db),
            current_user=Depends(require_authenticated_user)) -> Dict[str, Any]:  # fmt: skip
    _require(current_user, SecurityRoles.RESTORE_FILES)
    if not body.target_dataset:
        raise HTTPException(
            status_code=422, detail=_("Name the new dataset to restore into")
        )
    return _queued(
        db, current_user, copy_id,
        lambda: runs.queue_restore(db, copy_id, body.dataset, body.snapshot,
                                   body.target_dataset, body.tier, _who(current_user),
                                   body.host_id),
        "Off-site cloud copy restore started",
    )  # fmt: skip


@router.post("/backups/offsite/{copy_id}/export")
def export_keys(copy_id: str, body: ExportBody, db: Session = Depends(get_tenant_db),
                current_user=Depends(require_authenticated_user)) -> Response:  # fmt: skip
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    _require(current_user, SecurityRoles.RESTORE_FILES)
    recipient = body.recipient_key or getattr(
        escrow_target(db), "escrow_public_key", None
    )
    if not recipient:
        raise HTTPException(
            status_code=422,
            detail=_("Paste the OpenPGP public key to seal the export to"),
        )
    try:
        name, sealed, summary = export.export(db, copy_id, recipient, body.reason,
                                              _who(current_user))  # fmt: skip
    except offsite.OffsiteRefused as error:
        raise _refused(error) from error
    except breakglass.BreakGlassRefused as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused
    except breakglass.BreakGlassError as failed:
        raise HTTPException(status_code=503, detail=str(failed)) from failed
    _log(db, current_user, offsite.get_copy(db, copy_id), "Off-site cloud copy keys exported",
         {"recipient": summary["recipient"], "reason": summary["reason"],
          "keys": summary["keys"]})  # fmt: skip
    db.commit()
    return Response(content=sealed, media_type="application/pgp-encrypted",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Cache-Control": "no-store"})  # fmt: skip
