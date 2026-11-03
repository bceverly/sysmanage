# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""iCloud Photos to local (ROADMAP 24.12, Community).

Everything here runs on the backup target's STORAGE HOST, never on a
backed-up host.

``GET /backups/cloud`` -- the storage host, whether iCloud backup is enabled
there (and what got installed), and every account with its status.
``GET /backups/cloud/summary`` -- counts for the dashboard.
``GET /backups/cloud/runs`` (``?account_id``) -- recent jobs.

Manage Cloud Backups:

* ``POST /backups/cloud/enable`` -- "Enable iCloud backup": one push installs
  the pinned icloudpd, prepares the cloud root under the storage path and the
  root-only session directory.  Pressing it again repairs or upgrades.
* ``POST /backups/cloud/accounts`` / ``PUT`` / ``DELETE .../{id}`` -- an
  iCloud account.  Its password goes straight to OpenBAO and is never
  returned, logged or stored in the database.  Deleting one removes its
  sign-in from the storage host and its password from OpenBAO; its photos
  stay where they are.
* ``POST .../{id}/connect`` -- sign in (two-factor); ``POST
  /backups/cloud/runs/{run_id}/code`` -- the code the operator received.
* ``POST .../{id}/libraries`` -- list the account's libraries.
* ``POST .../{id}/run-now`` -- download now.

Every change, sign-in and run is audited.  An air-gapped repository
appliance has no internet, so the feature is hidden there (404).
"""

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import cloud_backup_jobs as cloud
from backend.services import cloud_backup_secrets as secrets
from backend.services import cloud_backup_views as views
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

MAX_ACCOUNTS = 20


class AccountSettings(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    library: str = Field(default="PrimarySync", max_length=128)
    enabled: bool = True
    interval_hours: int = 24
    window_start_hour: Optional[int] = None
    until_found: int = cloud.DEFAULT_UNTIL_FOUND
    # Deletes photos from iCloud once they are local: off unless asked, with
    # an explicit acknowledgment.
    auto_delete: bool = False
    acknowledge_auto_delete: bool = False


class AccountCreate(AccountSettings):
    apple_id: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class AccountUpdate(AccountSettings):
    # A new password replaces the old one in OpenBAO; omitted = unchanged.
    password: Optional[str] = Field(default=None, max_length=1024)


class CodeBody(BaseModel):
    code: str = Field(min_length=6, max_length=16)


def _available() -> None:
    if cloud.airgapped():
        raise HTTPException(status_code=404, detail=_("Not available on this server"))


def _require(current_user) -> None:
    role = SecurityRoles.MANAGE_CLOUD_BACKUPS
    if not current_user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _refused(refused: cloud.CloudBackupRefused) -> HTTPException:
    return HTTPException(status_code=refused.status, detail=str(refused))


def _audit(db, current_user, entity_id, name, description, details=None) -> None:
    AuditService.log(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(entity_id) if entity_id else None,
        entity_name=name,
        description=description,
        details=details or {},
        commit=False,
    )


def _account_or_404(db: Session, account_id: str) -> models.CloudBackupAccount:
    try:
        key = uuid.UUID(str(account_id))
    except ValueError:
        key = None
    account = (
        db.query(models.CloudBackupAccount)
        .filter(models.CloudBackupAccount.id == key)
        .first()
        if key
        else None
    )
    if account is None:
        raise HTTPException(status_code=404, detail=_("Cloud backup account not found"))
    return account


def _in_range(value: Optional[int], low: int, high: int, label: str) -> None:
    if value is not None and not low <= value <= high:
        raise HTTPException(
            status_code=422,
            detail=_("%s is out of range") % label + f" ({low}-{high})",
        )


def _validate(body: AccountSettings) -> str:
    _in_range(body.interval_hours, 1, 720, _("Interval (hours)"))
    _in_range(body.window_start_hour, 0, 23, _("Window start hour"))
    _in_range(body.until_found, 1, 10000, _("Stop after photos already present"))
    if body.auto_delete and not body.acknowledge_auto_delete:
        raise HTTPException(
            status_code=409,
            detail=_(
                "Confirm that photos will be deleted from iCloud once they are "
                "downloaded"
            ),
        )
    try:
        return cloud.valid_library(body.library)
    except cloud.CloudBackupRefused as refused:
        raise _refused(refused) from refused


def _apply(account: models.CloudBackupAccount, body: AccountSettings, library: str):
    account.display_name = body.display_name.strip()
    account.library = library
    account.enabled = body.enabled
    account.interval_hours = body.interval_hours
    account.window_start_hour = body.window_start_hour
    account.until_found = body.until_found
    account.auto_delete = body.auto_delete
    account.updated_at = cloud.now()


def _settings(body: AccountSettings) -> Dict[str, Any]:
    """What an audit records: the settings, never the password."""
    return body.model_dump(exclude={"password", "acknowledge_auto_delete"})


# --- reading ------------------------------------------------------------------


@router.get("/backups/cloud")
async def cloud_overview(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    return views.overview(db)


@router.get("/backups/cloud/summary")
async def cloud_summary(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    return views.summary(db)


@router.get("/backups/cloud/runs")
async def cloud_runs(
    account_id: Optional[str] = Query(default=None),
    limit: int = Query(default=views.RUN_LIMIT, ge=1, le=200),
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    _available()
    key = _account_or_404(db, account_id).id if account_id else None
    return {"runs": views.runs(db, key, limit)}


# --- enabling -----------------------------------------------------------------


@router.post("/backups/cloud/enable")
async def cloud_enable(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _available()
    _require(current_user)
    try:
        target, host = cloud.target_and_storage(db)
        if _enabling(db, target.id):
            raise cloud.CloudBackupRefused(
                409, _("iCloud backup is already being enabled")
            )
        run = cloud.queue_enable(db, target, host, current_user.userid)
    except cloud.CloudBackupRefused as refused:
        db.rollback()
        raise _refused(refused) from refused
    _audit(db, current_user, host.id, host.fqdn, "iCloud backup enable requested",
           {"run_id": str(run.id)})  # fmt: skip
    db.commit()
    return views.overview(db)


def _enabling(db: Session, target_id) -> bool:
    """An enable whose job is still queued or running."""
    row = cloud.enable_row(db, target_id)
    if row is None or row.status != cloud.RUNNING or row.run_id is None:
        return False
    run = (
        db.query(models.CloudBackupRun)
        .filter(models.CloudBackupRun.id == row.run_id)
        .first()
    )
    return run is not None and run.status in cloud.PENDING


# --- accounts -----------------------------------------------------------------


@router.post("/backups/cloud/accounts")
async def cloud_account_create(
    body: AccountCreate,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _available()
    _require(current_user)
    library = _validate(body)
    try:
        apple_id = cloud.valid_apple_id(body.apple_id)
        target, _host = cloud.target_and_storage(db)
    except cloud.CloudBackupRefused as refused:
        raise _refused(refused) from refused
    existing = views.accounts(db, target.id)
    if len(existing) >= MAX_ACCOUNTS:
        raise HTTPException(status_code=409, detail=_("Too many cloud accounts"))
    if any(
        a.apple_id.lower() == apple_id.lower() and a.library == library
        for a in existing
    ):
        raise HTTPException(
            status_code=409, detail=_("This Apple ID and library are already added")
        )
    account_id = uuid.uuid4()
    try:
        reference = secrets.store_password(account_id, body.password)
    except cloud.CloudBackupRefused as refused:
        raise _refused(refused) from refused
    except Exception as error:  # the vault's own message says why
        raise HTTPException(
            status_code=503,
            detail=_("OpenBAO could not store the password: %s") % error,
        ) from error
    now = cloud.now()
    account = models.CloudBackupAccount(
        id=account_id,
        target_id=target.id,
        provider=cloud.PROVIDER,
        apple_id=apple_id,
        dir_name=cloud.dir_name_for(account_id),
        password_ref=reference,
        password_set_at=now,
        state=cloud.STATE_NEW,
        created_by=current_user.userid,
        created_at=now,
    )
    _apply(account, body, library)
    db.add(account)
    db.flush()
    _audit(db, current_user, account.id, account.display_name,
           "iCloud account added", {"apple_id": apple_id, **_settings(body)})  # fmt: skip
    db.commit()
    return views.account_dict(db, account)


@router.put("/backups/cloud/accounts/{account_id}")
async def cloud_account_update(
    account_id: str,
    body: AccountUpdate,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _available()
    _require(current_user)
    account = _account_or_404(db, account_id)
    library = _validate(body)
    old_reference = None
    if body.password:
        try:
            reference = secrets.store_password(account.id, body.password)
        except Exception as error:  # the vault's own message says why
            raise HTTPException(
                status_code=503,
                detail=_("OpenBAO could not store the password: %s") % error,
            ) from error
        old_reference, account.password_ref = account.password_ref, reference
        account.password_set_at = cloud.now()
    _apply(account, body, library)
    _audit(db, current_user, account.id, account.display_name,
           "iCloud account changed",
           {**_settings(body), "password_changed": bool(body.password)})  # fmt: skip
    db.commit()
    secrets.delete_password(old_reference)
    return views.account_dict(db, account)


@router.delete("/backups/cloud/accounts/{account_id}")
async def cloud_account_delete(
    account_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """The sign-in is removed from the storage host and the password from
    OpenBAO.  The photos already downloaded stay on the storage."""
    _available()
    _require(current_user)
    account = _account_or_404(db, account_id)
    removal = None
    try:
        removal = cloud.queue_account_run(
            db, account, cloud.REMOVE, current_user.userid
        )
    except cloud.CloudBackupRefused as refused:
        # No storage host to tell: the account goes anyway (its session
        # directory is removed by the next Enable, which keeps only known ones).
        db.rollback()
        account = _account_or_404(db, account_id)
        removal_reason = str(refused)
    else:
        removal_reason = None
    reference = account.password_ref
    name, apple_id = account.display_name, account.apple_id
    db.query(models.CloudBackupRun).filter(
        models.CloudBackupRun.account_id == account.id,
        models.CloudBackupRun.status.in_(cloud.PENDING),
        models.CloudBackupRun.action != cloud.REMOVE,
    ).update(
        {"status": cloud.FAILED, "finished_at": cloud.now(), "mfa_code": None,
         "message": "account deleted"},
        synchronize_session=False,
    )  # fmt: skip
    db.delete(account)
    _audit(db, current_user, account_id, name, "iCloud account deleted",
           {"apple_id": apple_id,
            "removal_run": str(removal.id) if removal else None,
            "removal_refused": removal_reason})  # fmt: skip
    db.commit()
    secrets.delete_password(reference)
    return {"deleted": True, "photos_kept": True}


def _run_job(db, current_user, account_id: str, action: str, label: str):
    _available()
    _require(current_user)
    account = _account_or_404(db, account_id)
    if action != cloud.CONNECT and account.session_created_at is None:
        raise HTTPException(
            status_code=409, detail=_("Sign in to this account first (Connect)")
        )
    try:
        run = cloud.queue_account_run(db, account, action, current_user.userid)
    except cloud.CloudBackupRefused as refused:
        db.rollback()
        raise _refused(refused) from refused
    _audit(db, current_user, account.id, account.display_name, label,
           {"run_id": str(run.id)})  # fmt: skip
    db.commit()
    return views.run_dict(run)


@router.post("/backups/cloud/accounts/{account_id}/connect")
async def cloud_account_connect(
    account_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return _run_job(
        db, current_user, account_id, cloud.CONNECT, "iCloud sign-in started"
    )


@router.post("/backups/cloud/accounts/{account_id}/libraries")
async def cloud_account_libraries(
    account_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return _run_job(
        db, current_user, account_id, cloud.LIBRARIES, "iCloud libraries listed"
    )


@router.post("/backups/cloud/accounts/{account_id}/run-now")
async def cloud_account_run_now(
    account_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Asks the scheduler for a download now; it starts as soon as the
    target has a free slot (it shares the fleet's concurrency cap)."""
    _available()
    _require(current_user)
    account = _account_or_404(db, account_id)
    if account.session_created_at is None:
        raise HTTPException(
            status_code=409, detail=_("Sign in to this account first (Connect)")
        )
    if not cloud.enabled(db, account.target_id):
        raise HTTPException(
            status_code=409,
            detail=_("Enable iCloud backup on the storage host first"),
        )
    if cloud.pending(db, account_id=account.id):
        raise HTTPException(
            status_code=409,
            detail=_("A job for this account is already queued or running"),
        )
    account.run_requested_at = cloud.now()
    _audit(db, current_user, account.id, account.display_name,
           "iCloud download requested")  # fmt: skip
    # pylint: disable=import-outside-toplevel
    from backend.services import backup_jobs  # noqa: PLC0415
    from backend.services import cloud_backup_tick  # noqa: PLC0415

    try:
        target, host = cloud.target_and_storage(db)
        cloud_backup_tick.start_due(db, target, host, backup_jobs.now())
    except cloud.CloudBackupRefused as refused:
        db.rollback()
        raise _refused(refused) from refused
    db.commit()
    return views.account_dict(db, account)


@router.post("/backups/cloud/runs/{run_id}/code")
async def cloud_run_code(
    run_id: str,
    body: CodeBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """The two-factor code for a sign-in that is waiting for one.  Held on
    the run only until the storage host's job collects it."""
    _available()
    _require(current_user)
    try:
        key = uuid.UUID(str(run_id))
    except ValueError:
        key = None
    run = (
        db.query(models.CloudBackupRun).filter(models.CloudBackupRun.id == key).first()
        if key
        else None
    )
    if run is None:
        raise HTTPException(status_code=404, detail=_("Cloud backup run not found"))
    try:
        secrets.submit_code(db, run, body.code)
    except cloud.CloudBackupRefused as refused:
        raise _refused(refused) from refused
    # Audited without the code itself.
    _audit(db, current_user, run.account_id, None, "iCloud two-factor code entered",
           {"run_id": str(run.id)})  # fmt: skip
    db.commit()
    return views.run_dict(run)
