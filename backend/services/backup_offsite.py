# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The off-site cloud copy: S3 Glacier Deep Archive (ROADMAP 27.3).

"Two is one, one is none": an encrypted copy of the storage host's
datasets, in the operator's own S3 bucket, for the day the site is gone.
The storage host's agent reads, encrypts (AES-256, a key only the operator
holds) and uploads straight to AWS; no backup data passes through this
server, which keeps the settings and the record of what is in the bucket.

Editions (Bryan, 2026-11-19): setting the copy up and keeping it running --
the settings, the schedule, retention, the key's creation and rotation -- is
Professional+ (``backup_engine``).  Everything that gets the data back is
here and works with no license and after a lapse ("never hold safety
hostage"): the record of what is in the bucket, the restore, the key export,
and turning the copy OFF.  A lapse freezes the copy: no new uploads, the
bucket and its record stay, restores keep working.

An air-gapped site has no off-site cloud copy: it is hidden there, like
iCloud (nothing on such a site may reach out).
"""

import json
import re
import urllib.parse
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_offsite_secrets as secrets

QUEUED, RUNNING = "queued", "running"
OK, PARTIAL, FAILED, INTERRUPTED = "ok", "partial", "failed", "interrupted"
PENDING = (QUEUED, RUNNING)
CHECK, UPLOAD, RESTORE = "check", "upload", "restore"
STORAGE_CLASSES = ("DEEP_ARCHIVE", "GLACIER", "GLACIER_IR", "STANDARD_IA", "STANDARD")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_REGION = re.compile(r"^[a-z0-9-]{1,32}$")
_PREFIX = re.compile(r"^[A-Za-z0-9_.()!*'/-]{0,200}$")
_ACCESS_KEY = re.compile(r"^[A-Z0-9]{16,128}$")


class OffsiteRefused(Exception):
    """A request the server will not carry out; ``status`` is the HTTP
    status and ``code`` a stable reason."""

    def __init__(self, status: int, message: str, code: str = "refused"):
        super().__init__(message)
        self.status = status
        self.code = code


def now() -> datetime:
    return datetime.utcnow()


def engine():
    """backup_engine when loaded and new enough for the off-site copy; None
    otherwise (Community, or a lapse)."""
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import module_loader  # noqa: PLC0415

    module = module_loader.get_module("backup_engine")
    return module if module is not None and hasattr(module, "offsite_plan") else None


def need_engine():
    found = engine()
    if found is None:
        raise OffsiteRefused(
            402,
            _("Setting up and running the off-site cloud copy needs Professional+; "
              "restoring from it and exporting its keys do not"),
            "license",
        )  # fmt: skip
    return found


def airgapped() -> bool:
    # pylint: disable=import-outside-toplevel
    from backend.services import server_config_service  # noqa: PLC0415

    return server_config_service.get_server_role() == "repository"


def settings_of(copy: models.BackupOffsiteCopy) -> Dict[str, Any]:
    try:
        value = json.loads(copy.settings or "{}")
    except ValueError:
        value = {}
    return value if isinstance(value, dict) else {}


def get_copy(db: Session, copy_id: Any) -> models.BackupOffsiteCopy:
    try:
        key = uuid.UUID(str(copy_id))
    except ValueError:
        key = None
    copy = db.get(models.BackupOffsiteCopy, key) if key else None
    if copy is None:
        raise OffsiteRefused(404, _("No such off-site copy"), "not_found")
    return copy


def copies(db: Session) -> List[models.BackupOffsiteCopy]:
    return (
        db.query(models.BackupOffsiteCopy)
        .order_by(models.BackupOffsiteCopy.created_at)
        .all()
    )


def target_and_host(db: Session, copy_or_target_id: Any):
    target = db.get(models.BackupTarget, uuid.UUID(str(copy_or_target_id)))
    if target is None:
        raise OffsiteRefused(404, _("No such backup target"), "not_found")
    host = jobs.storage_host(db, target)
    if host is None or not target.storage_path:
        raise OffsiteRefused(
            409, _("The backup target has no storage host to run on"), "no_storage_host"
        )
    return target, host


# --- checking what an operator enters --------------------------------------------------


def _endpoint(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    parts = urllib.parse.urlsplit(str(value).strip())
    if (parts.scheme not in ("https", "http") or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment):  # fmt: skip
        raise OffsiteRefused(
            422, _("The endpoint must be a plain https:// address"), "invalid_endpoint"
        )
    return str(value).strip().rstrip("/")


def _location(
    data: Dict[str, Any], copy: Optional[models.BackupOffsiteCopy]
) -> Dict[str, Any]:
    def given(field, default=None):
        if field in data:
            return data[field]
        return getattr(copy, field) if copy is not None else default

    bucket = str(given("bucket") or "").strip()
    if not _BUCKET.match(bucket) or ".." in bucket:
        raise OffsiteRefused(422, _("Enter the S3 bucket's name"), "invalid_bucket")
    region = str(given("region") or "us-east-1").strip()
    if not _REGION.match(region):
        raise OffsiteRefused(422, _("Enter the bucket's AWS region"), "invalid_region")
    prefix = str(given("prefix") or "").strip().strip("/")
    if not _PREFIX.match(prefix) or ".." in prefix.split("/") or "//" in prefix:
        raise OffsiteRefused(
            422,
            _("The prefix may hold letters, digits and - _ . / only"),
            "invalid_prefix",
        )
    storage_class = str(given("storage_class") or "DEEP_ARCHIVE")
    if storage_class not in STORAGE_CLASSES:
        raise OffsiteRefused(422, _("Choose a storage class"), "invalid_storage_class")
    return {"bucket": bucket, "region": region, "prefix": prefix,
            "storage_class": storage_class, "endpoint": _endpoint(given("endpoint")),
            "object_lock": bool(given("object_lock", True))}  # fmt: skip


def _credentials(data: Dict[str, Any], required: bool) -> Optional[Dict[str, str]]:
    access = str(data.get("access_key") or "").strip()
    secret = str(data.get("secret_key") or "").strip()
    if not access and not secret and not required:
        return None
    if not _ACCESS_KEY.match(access) or not secret or len(secret) > 256:
        raise OffsiteRefused(
            422,
            _("Enter the access key ID and secret access key"),
            "invalid_credentials",
        )
    return {"access_key": access, "secret_key": secret}


def _settings(found_engine, raw: Any) -> Dict[str, Any]:
    try:
        return found_engine.offsite_settings(raw)
    except ValueError as error:
        raise OffsiteRefused(
            422, str(error), getattr(error, "code", "invalid_settings")
        ) from error


# --- setting the copy up (Professional+) ------------------------------------------------


def create(
    db: Session, data: Dict[str, Any], actor: str, vault=None
) -> models.BackupOffsiteCopy:
    found = need_engine()
    if airgapped():
        raise OffsiteRefused(
            409, _("An air-gapped site has no off-site cloud copy"), "airgapped"
        )
    target, _host = target_and_host(db, data.get("target_id") or "")
    if db.query(models.BackupOffsiteCopy).filter_by(target_id=target.id).first():
        raise OffsiteRefused(
            409, _("This target already has an off-site copy"), "exists"
        )
    location = _location(data, None)
    creds = _credentials(data, required=True)
    settings = _settings(found, data.get("settings"))
    copy = models.BackupOffsiteCopy(
        id=uuid.uuid4(), target_id=target.id, enabled=True, settings=json.dumps(settings),
        created_by=actor, created_at=now(), access_key_hint=creds["access_key"][-4:],
        **location,
    )  # fmt: skip
    copy.credentials_ref = secrets.store_credentials(copy.id, creds["access_key"],
                                                     creds["secret_key"], vault=vault)  # fmt: skip
    kid, ref = secrets.new_key(copy.id, vault)
    db.add(copy)
    db.add(models.BackupOffsiteKey(id=uuid.uuid4(), copy_id=copy.id, key_id=kid, key_ref=ref,
                                   created_by=actor, created_at=now()))  # fmt: skip
    copy.next_run_at = found.offsite_next_run(settings, now())
    db.flush()
    return copy


def update(db: Session, copy_id: Any, data: Dict[str, Any], actor: str,
           vault=None) -> models.BackupOffsiteCopy:  # fmt: skip
    """Change the settings (Professional+).  Turning the copy OFF alone works
    in every edition; anything else needs the engine."""
    copy = get_copy(db, copy_id)
    if set(data) <= {"enabled"} and data.get("enabled") is False:
        copy.enabled = False
        copy.updated_by, copy.updated_at = actor, now()
        return copy
    found = need_engine()
    location = _location(data, copy)
    for field, value in location.items():
        setattr(copy, field, value)
    if "settings" in data:
        settings = _settings(found, data.get("settings"))
        copy.settings = json.dumps(settings)
        copy.next_run_at = found.offsite_next_run(settings, now())
    if "enabled" in data:
        copy.enabled = bool(data["enabled"])
    creds = _credentials(data, required=False)
    if creds is not None:
        old = copy.credentials_ref
        copy.credentials_ref = secrets.store_credentials(copy.id, creds["access_key"],
                                                         creds["secret_key"], vault=vault)  # fmt: skip
        copy.access_key_hint = creds["access_key"][-4:]
        copy.lock_verified, copy.checked_at = None, None
        if old != copy.credentials_ref:
            secrets.delete(old, vault)
    copy.updated_by, copy.updated_at = actor, now()
    return copy


def rotate_key(db: Session, copy_id: Any, actor: str, vault=None) -> str:
    """A new key for what is uploaded from now on (Professional+).  The old
    key is kept -- retired -- for everything already in the bucket, and the
    next upload of every dataset is a full under the new key."""
    need_engine()
    copy = get_copy(db, copy_id)
    old = secrets.current_key(db, copy.id)
    kid, ref = secrets.new_key(copy.id, vault)
    if old is not None:
        old.retired_at = now()
    db.add(models.BackupOffsiteKey(id=uuid.uuid4(), copy_id=copy.id, key_id=kid, key_ref=ref,
                                   created_by=actor, created_at=now()))  # fmt: skip
    copy.updated_by, copy.updated_at = actor, now()
    db.flush()
    return kid


# --- what is in the bucket ----------------------------------------------------------------


def streams(
    db: Session, copy_id: Any, live_only: bool = True
) -> List[models.BackupOffsiteStream]:
    query = db.query(models.BackupOffsiteStream).filter(
        models.BackupOffsiteStream.copy_id == copy_id
    )
    if live_only:
        query = query.filter(models.BackupOffsiteStream.expires_at > now())
    return query.order_by(models.BackupOffsiteStream.dataset,
                          models.BackupOffsiteStream.uploaded_at).all()  # fmt: skip


def days_in_use(db: Session, copy: models.BackupOffsiteCopy) -> List[int]:
    rows = (
        db.query(models.BackupOffsiteStream.retention_days)
        .filter(models.BackupOffsiteStream.copy_id == copy.id).distinct().all()
    )  # fmt: skip
    found = {int(r[0]) for r in rows}
    module = engine()
    if module is not None:
        days = module.offsite_retention(module.offsite_settings(settings_of(copy)),
                                        copy.storage_class)  # fmt: skip
        found |= {days["incremental"], days["monthly"], days["yearly"]}
    return sorted(found)


def setup_help(db: Session, copy: models.BackupOffsiteCopy) -> Optional[Dict[str, Any]]:
    """What the operator applies to the bucket and the IAM user (Pro+)."""
    module = engine()
    if module is None:
        return None
    lifecycle = module.offsite_lifecycle(copy.prefix or "", days_in_use(db, copy))
    policy = module.offsite_iam_policy(copy.bucket, copy.prefix or "")
    return {"lifecycle": lifecycle, "iam_policy": policy, "commands": _commands(copy)}


def _commands(copy: models.BackupOffsiteCopy) -> List[str]:
    bucket, region = copy.bucket, copy.region
    location = ("" if region == "us-east-1"
                else f" --create-bucket-configuration LocationConstraint={region}")  # fmt: skip
    return [
        f"aws s3api create-bucket --bucket {bucket} --region {region}{location} "
        "--object-lock-enabled-for-bucket",
        f"aws s3api put-public-access-block --bucket {bucket} --public-access-block-configuration "
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,"
        "RestrictPublicBuckets=true",
        f"aws s3api put-bucket-lifecycle-configuration --bucket {bucket} "
        "--lifecycle-configuration file://lifecycle.json",
        "aws iam create-user --user-name sysmanage-offsite",
        "aws iam put-user-policy --user-name sysmanage-offsite --policy-name "
        "sysmanage-offsite --policy-document file://iam-policy.json",
        "aws iam create-access-key --user-name sysmanage-offsite",
    ]


def summary(db: Session, copy: models.BackupOffsiteCopy) -> Dict[str, Any]:
    """Per dataset: its newest restore point and what is stored."""
    found: Dict[str, Dict[str, Any]] = {}
    for row in streams(db, copy.id):
        entry = found.setdefault(row.dataset, {"dataset": row.dataset, "bytes_stored": 0,
                                               "streams": 0, "last_full_at": None})  # fmt: skip
        entry["bytes_stored"] += int(row.bytes_stored or 0)
        entry["streams"] += 1
        entry["last_snapshot"] = row.snapshot
        entry["last_uploaded_at"] = row.uploaded_at.isoformat()
        entry["key_id"] = row.key_id
        if row.kind == "full":
            entry["last_full_at"] = row.uploaded_at.isoformat()
    return found


def view(db: Session, copy: models.BackupOffsiteCopy) -> Dict[str, Any]:
    module = engine()
    datasets = summary(db, copy)
    stored = sum(d["bytes_stored"] for d in datasets.values())
    current = secrets.current_key(db, copy.id)
    settings = settings_of(copy)
    out = {
        "id": str(copy.id), "target_id": str(copy.target_id), "enabled": copy.enabled,
        "bucket": copy.bucket, "region": copy.region, "endpoint": copy.endpoint,
        "prefix": copy.prefix, "storage_class": copy.storage_class,
        "object_lock": copy.object_lock, "lock_verified": copy.lock_verified,
        "checked_at": _iso(copy.checked_at), "access_key_hint": copy.access_key_hint,
        "settings": settings, "next_run_at": _iso(copy.next_run_at),
        "last_ok_at": _iso(copy.last_ok_at), "last_error": copy.last_error,
        "last_run_id": str(copy.last_run_id) if copy.last_run_id else None,
        "key_id": current.key_id if current else None,
        "datasets": sorted(datasets.values(), key=lambda d: d["dataset"]),
        "bytes_stored": stored, "licensed": module is not None,
        "overdue": overdue(copy),
    }  # fmt: skip
    if module is not None:
        normalized = module.offsite_settings(settings)
        out["cost"] = module.offsite_cost(normalized, copy.storage_class, stored)
        out["retention_days"] = module.offsite_retention(normalized, copy.storage_class)
    return out


OVERDUE_HOURS = 48


def overdue(copy: models.BackupOffsiteCopy, at: Optional[datetime] = None) -> bool:
    """No good upload in two days on a copy that is on (24.6-style alert)."""
    if not copy.enabled:
        return False
    since = copy.last_ok_at or copy.created_at
    return (
        since is not None
        and ((at or now()) - since).total_seconds() > OVERDUE_HOURS * 3600
    )


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None
