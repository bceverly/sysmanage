# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The off-site copy's jobs on the storage host (ROADMAP 27.3).

* ``check``   -- the bucket takes an upload with these credentials, and
  whether Object Lock is on (any edition: it reads nothing back);
* ``upload``  -- one run of the copy, planned by the Pro+ engine (which
  datasets build on which snapshot, how long each class is kept), started
  by the leader's tick at the copy's hour or by "Run now";
* ``restore`` -- Community: thaw a dataset's chain (its full and the
  incrementals up to the chosen point) and ``zfs receive`` it into a NEW
  dataset on a storage host.  Planned from the record here, so nothing is
  thawed to find out what to thaw; the thaw's cost is estimated first.

The agent answers with ``offsite_cloud_progress`` and one
``offsite_cloud_result`` per run; a message for a run of another host is
ignored and logged.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import backup_offsite as offsite
from backend.services import backup_offsite_secrets as secrets
from backend.services import config_mgmt_dispatch, queue_clock
from backend.services.agent_capability_service import UnsupportedCapabilityError

logger = logging.getLogger(__name__)

COMMAND = "offsite_cloud_run"
_TEXT_LIMIT = 16000
_END = (offsite.OK, offsite.PARTIAL, offsite.FAILED, offsite.INTERRUPTED)
# Restore pricing at the time of writing (2026-11, US East), per GB and per
# 1000 requests; data transferred out of AWS on top.  An estimate only.
THAW_PRICES = {
    "DEEP_ARCHIVE": {"Bulk": (0.0025, 0.025), "Standard": (0.02, 0.10)},
    "GLACIER": {"Bulk": (0.0, 0.0), "Standard": (0.01, 0.05)},
}
THAW_HOURS = {"DEEP_ARCHIVE": {"Bulk": 48, "Standard": 12},
              "GLACIER": {"Bulk": 12, "Standard": 5}}  # fmt: skip
TRANSFER_PER_GB = 0.09


def _pending(db: Session, copy_id: Any) -> Optional[models.BackupOffsiteRun]:
    return (
        db.query(models.BackupOffsiteRun)
        .filter(models.BackupOffsiteRun.copy_id == copy_id,
                models.BackupOffsiteRun.status.in_(offsite.PENDING))  # fmt: skip
        .first()
    )


def _base_parameters(
    copy: models.BackupOffsiteCopy, run_id: Any, action: str
) -> Dict[str, Any]:
    return {"run_id": str(run_id), "copy_id": str(copy.id), "action": action,
            "bucket": copy.bucket, "region": copy.region, "endpoint": copy.endpoint,
            "prefix": copy.prefix or ""}  # fmt: skip


def _queue(db: Session, copy: models.BackupOffsiteCopy, host: models.Host, action: str,
           parameters: Dict[str, Any], actor: str, **fields: Any) -> models.BackupOffsiteRun:  # fmt: skip
    if _pending(db, copy.id) is not None:
        raise offsite.OffsiteRefused(
            409, _("An off-site job for this copy is already queued or running"), "busy"
        )
    run = models.BackupOffsiteRun(
        id=uuid.UUID(parameters["run_id"]), copy_id=copy.id, host_id=host.id, action=action,
        status=offsite.QUEUED, queued_at=offsite.now(), requested_by=actor, **fields,
    )  # fmt: skip
    db.add(run)
    db.flush()
    try:
        run.command_id = config_mgmt_dispatch.queue_command(
            db, host.id, COMMAND, parameters
        )
    except UnsupportedCapabilityError as refused:
        db.delete(run)
        raise offsite.OffsiteRefused(409, str(refused), "unsupported") from refused
    copy.last_run_id = run.id
    db.flush()
    return run


def _host(
    db: Session, copy: models.BackupOffsiteCopy, host_id: Any = None
) -> models.Host:
    if host_id:
        host = db.get(models.Host, uuid.UUID(str(host_id)))
        if host is None:
            raise offsite.OffsiteRefused(404, _("No such host"), "not_found")
        return host
    _target, host = offsite.target_and_host(db, copy.target_id)
    return host


def queue_check(db: Session, copy_id: Any, actor: str) -> models.BackupOffsiteRun:
    """Any edition: it proves the credentials, it copies nothing."""
    copy = offsite.get_copy(db, copy_id)
    run_id = uuid.uuid4()
    current = secrets.current_key(db, copy.id)
    return _queue(db, copy, _host(db, copy), offsite.CHECK,
                  _base_parameters(copy, run_id, offsite.CHECK), actor,
                  key_id=current.key_id if current else None)  # fmt: skip


def _seen(db: Session, copy: models.BackupOffsiteCopy) -> Dict[str, Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for row in offsite.streams(db, copy.id):
        entry = seen.setdefault(row.dataset, {"last_full_at": None})
        entry["last_snapshot"] = row.snapshot
        entry["key_id"] = row.key_id
        if row.kind == "full":
            entry["last_full_at"] = row.uploaded_at
    return seen


def _yearly_done(db: Session, copy: models.BackupOffsiteCopy, at: datetime) -> bool:
    module = offsite.engine()
    days = module.offsite_retention(module.offsite_settings(offsite.settings_of(copy)),
                                    copy.storage_class)  # fmt: skip
    start = datetime(at.year, 1, 1)
    return (
        db.query(models.BackupOffsiteStream.id)
        .filter(models.BackupOffsiteStream.copy_id == copy.id,
                models.BackupOffsiteStream.kind == "full",
                models.BackupOffsiteStream.retention_days == days["yearly"],
                models.BackupOffsiteStream.uploaded_at >= start)  # fmt: skip
        .first()
        is not None
    )


def upload_parameters(db: Session, copy: models.BackupOffsiteCopy, run_id: Any,
                      key_id: str, at: datetime) -> Dict[str, Any]:  # fmt: skip
    module = offsite.need_engine()
    target, _host = offsite.target_and_host(db, copy.target_id)
    settings = module.offsite_settings(offsite.settings_of(copy))
    plan = module.offsite_plan(settings, copy.storage_class, key_id, _seen(db, copy),
                               _yearly_done(db, copy, at), at)  # fmt: skip
    params = _base_parameters(copy, run_id, offsite.UPLOAD)
    params.update({
        "storage_path": target.storage_path, "storage_class": copy.storage_class,
        "object_lock": bool(copy.object_lock), "retention": plan["retention"],
        "exclude": settings["exclude"], "include": settings["include"],
        "bases": plan["bases"], "bandwidth": settings["bandwidth"],
        "part_bytes": int(settings["part_mib"]) << 20,
    })  # fmt: skip
    return params


def queue_upload(db: Session, copy_id: Any, actor: str) -> models.BackupOffsiteRun:
    """One run of the copy (Professional+)."""
    copy = offsite.get_copy(db, copy_id)
    offsite.need_engine()
    if not copy.enabled:
        raise offsite.OffsiteRefused(
            409, _("This off-site copy is turned off"), "disabled"
        )
    current = secrets.current_key(db, copy.id)
    if current is None:
        raise offsite.OffsiteRefused(409, _("This off-site copy has no key"), "no_key")
    run_id = uuid.uuid4()
    params = upload_parameters(db, copy, run_id, current.key_id, offsite.now())
    return _queue(db, copy, _host(db, copy), offsite.UPLOAD, params, actor,
                  key_id=current.key_id)  # fmt: skip


# --- restore (Community) ------------------------------------------------------------------


def _stream_dict(row: models.BackupOffsiteStream) -> Dict[str, Any]:
    return {
        "stream_id": str(row.id), "dataset": row.dataset, "kind": row.kind,
        "snapshot": row.snapshot, "base_snapshot": row.base_snapshot, "key_id": row.key_id,
        "storage_class": row.storage_class, "bytes_stored": int(row.bytes_stored or 0),
        "uploaded_at": row.uploaded_at.isoformat(), "expires_at": row.expires_at.isoformat(),
        "parts": json.loads(row.parts or "[]"),
    }  # fmt: skip


def chain(
    db: Session, copy_id: Any, dataset: str, snapshot: str
) -> List[Dict[str, Any]]:
    """The streams that rebuild ``dataset`` as of ``snapshot``: walking the
    bases back to a full.  Refused when a link has expired or never landed."""
    rows = {r.snapshot: r for r in offsite.streams(db, copy_id) if r.dataset == dataset}
    found: List[models.BackupOffsiteStream] = []
    current = rows.get(snapshot)
    while current is not None:
        found.append(current)
        if current.kind == "full":
            break
        current = rows.get(current.base_snapshot)
    if not found or found[-1].kind != "full":
        raise offsite.OffsiteRefused(
            409,
            _("This restore point's chain is not complete in the bucket"),
            "broken_chain",
        )
    if len({r.key_id for r in found}) != 1:
        raise offsite.OffsiteRefused(409, _("This chain spans two keys"), "mixed_keys")
    return [_stream_dict(r) for r in reversed(found)]


def restore_points(db: Session, copy_id: Any) -> List[Dict[str, Any]]:
    """Every point a dataset can be restored to, newest first, with its size."""
    points = []
    for row in offsite.streams(db, copy_id):
        try:
            links = chain(db, copy_id, row.dataset, row.snapshot)
        except offsite.OffsiteRefused:
            continue
        points.append({"dataset": row.dataset, "snapshot": row.snapshot,
                       "uploaded_at": row.uploaded_at.isoformat(), "streams": len(links),
                       "bytes": sum(s["bytes_stored"] for s in links)})  # fmt: skip
    return sorted(points, key=lambda p: (p["dataset"], p["uploaded_at"]), reverse=True)


def estimate(links: List[Dict[str, Any]], tier: str) -> Dict[str, Any]:
    """What thawing and downloading ``links`` costs, and how long the thaw
    takes -- shown before a restore starts."""
    size = sum(s["bytes_stored"] for s in links)
    parts = sum(len(s["parts"]) for s in links)
    storage = links[0]["storage_class"] if links else "STANDARD"
    per_gb, per_k = THAW_PRICES.get(storage, {}).get(tier, (0.0, 0.0))
    gigabytes = size / 1e9
    return {
        "bytes": size, "parts": parts, "storage_class": storage, "tier": tier,
        "thaw_hours": THAW_HOURS.get(storage, {}).get(tier, 0),
        "usd_thaw": round(gigabytes * per_gb + parts / 1000 * per_k, 2),
        "usd_transfer": round(gigabytes * TRANSFER_PER_GB, 2),
    }  # fmt: skip


def queue_restore(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session, copy_id: Any, dataset: str, snapshot: str, target_dataset: str,
    tier: str, actor: str, host_id: Any = None,
) -> models.BackupOffsiteRun:  # fmt: skip
    """Thaw and receive (any edition, also after a lapse)."""
    copy = offsite.get_copy(db, copy_id)
    if tier not in ("Bulk", "Standard"):
        raise offsite.OffsiteRefused(
            422, _("The thaw tier is Bulk or Standard"), "invalid_tier"
        )
    links = chain(db, copy.id, dataset, snapshot)
    run_id = uuid.uuid4()
    params = _base_parameters(copy, run_id, offsite.RESTORE)
    params.update({"streams": links, "target_dataset": target_dataset, "tier": tier})
    return _queue(db, copy, _host(db, copy, host_id), offsite.RESTORE, params, actor,
                  key_id=links[0]["key_id"], target_dataset=target_dataset,
                  snapshot=snapshot,
                  streams=json.dumps([s["stream_id"] for s in links]))  # fmt: skip


# --- the tick (the leader's) -----------------------------------------------------------------


def tick(db: Session, at: Optional[datetime] = None) -> Dict[str, int]:
    """Start each copy's upload at its hour.  Without the engine (Community,
    or a lapse) nothing starts: the copy is frozen, never deleted."""
    at = at or offsite.now()
    fail_silent(db, at)
    module = offsite.engine()
    out = {"started": 0, "skipped": 0}
    if module is None:
        return out
    for copy in offsite.copies(db):
        if not copy.enabled or copy.next_run_at is None or copy.next_run_at > at:
            continue
        settings = module.offsite_settings(offsite.settings_of(copy))
        copy.next_run_at = module.offsite_next_run(settings, at)
        if _pending(db, copy.id) is not None:
            out["skipped"] += 1  # an upload still going (they can take days)
            continue
        try:
            queue_upload(db, copy.id, "scheduler")
            out["started"] += 1
        except offsite.OffsiteRefused as refused:
            copy.last_error = str(refused)
            out["skipped"] += 1
    return out


SILENT = timedelta(hours=24)


def fail_silent(db: Session, at: datetime) -> int:
    """A run the storage host took and then said nothing about for a day is
    failed, so it stops holding the copy (an upload reports every part, a
    thaw every poll).  One a maintenance window still holds is waiting, not
    silent.  Any edition: a restore must not hang either."""
    failed = 0
    rows = db.query(models.BackupOffsiteRun).filter(
        models.BackupOffsiteRun.status.in_(offsite.PENDING)
    )
    for run in rows.all():
        started = queue_clock.clock_start(
            queue_clock.delivery(db, run.command_id), run.queued_at
        )
        heard = _heard_at(run) or started
        if heard is None or at - heard <= SILENT:
            continue
        run.status, run.finished_at = offsite.FAILED, at
        run.message = _("The storage host has said nothing about this job for a day")
        copy = db.get(models.BackupOffsiteCopy, run.copy_id)
        if copy is not None and run.action != offsite.RESTORE:
            copy.last_error = run.message
        failed += 1
    return failed


def _heard_at(run: models.BackupOffsiteRun) -> Optional[datetime]:
    try:
        seen = json.loads(run.progress or "{}").get("seen_at")
        return datetime.fromisoformat(seen) if seen else None
    except (ValueError, TypeError, AttributeError):
        return None


# --- what the agent reports --------------------------------------------------------------


def _run(
    db: Session, host_id: Any, payload: Dict[str, Any]
) -> Optional[models.BackupOffsiteRun]:
    try:
        key = uuid.UUID(str(payload.get("run_id")))
    except ValueError:
        logger.warning("off-site message with a bad run id from host %s", host_id)
        return None
    run = db.get(models.BackupOffsiteRun, key)
    if run is None or str(run.host_id) != str(host_id):
        logger.warning("off-site message for run %s from host %s ignored", key, host_id)
        return None
    return run


def record_progress(db: Session, host_id: Any, payload: Dict[str, Any]) -> None:
    run = _run(db, host_id, payload)
    if run is None or run.status not in offsite.PENDING:
        return
    run.status = offsite.RUNNING
    run.started_at = run.started_at or offsite.now()
    kept = {k: payload.get(k) for k in ("phase", "dataset", "part", "datasets_done",
                                        "datasets_total", "bytes_uploaded", "bytes_received",
                                        "parts_ready", "parts_total", "snapshot")}  # fmt: skip
    kept["seen_at"] = offsite.now().isoformat()
    run.progress = json.dumps({k: v for k, v in kept.items() if v is not None})


def _store_stream(
    db: Session, run: models.BackupOffsiteRun, stream: Dict[str, Any]
) -> bool:
    try:
        stream_id = uuid.UUID(str(stream.get("stream_id")))
        parts = stream["parts"]
        days = int(stream["retention_days"])
        uploaded = datetime.fromisoformat(str(stream["finished_at"])).replace(
            tzinfo=None
        )
        created = datetime.fromisoformat(str(stream["created_at"])).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError):
        logger.warning(
            "off-site run %s: a stream without its fields was ignored", run.id
        )
        return False
    if db.get(models.BackupOffsiteStream, stream_id) is not None:
        return False
    db.add(models.BackupOffsiteStream(
        id=stream_id, copy_id=run.copy_id, run_id=run.id, dataset=str(stream.get("dataset")),
        snapshot=str(stream.get("snapshot")), base_snapshot=stream.get("base_snapshot"),
        kind=str(stream.get("kind")), key_id=str(stream.get("key_id")),
        storage_class=str(stream.get("storage_class")), retention_days=days,
        parts=json.dumps(parts), part_count=len(parts),
        bytes_stored=sum(int(p.get("bytes") or 0) for p in parts),
        stream_bytes=int(stream.get("stream_bytes") or 0),
        manifest_key=str(stream.get("manifest_key")), created_at=created,
        uploaded_at=uploaded, expires_at=created + timedelta(days=days),
    ))  # fmt: skip
    return True


def record_result(db: Session, host_id: Any, payload: Dict[str, Any]) -> None:
    run = _run(db, host_id, payload)
    if run is None or run.status not in offsite.PENDING:
        return
    status = payload.get("status")
    run.status = status if status in _END else offsite.FAILED
    run.finished_at = offsite.now()
    errors = payload.get("errors") or []
    run.message = "\n".join(str(e) for e in errors)[-_TEXT_LIMIT:] or None
    copy = db.get(models.BackupOffsiteCopy, run.copy_id)
    if run.action == offsite.UPLOAD:
        streams = payload.get("streams") or []
        stored = sum(
            1 for s in streams if isinstance(s, dict) and _store_stream(db, run, s)
        )
        run.bytes_moved = int(payload.get("bytes_uploaded") or 0)
        run.snapshot = payload.get("snapshot")
        logger.info(
            "off-site run %s: %s, %d streams recorded", run.id, run.status, stored
        )
    else:
        if run.action == offsite.RESTORE:
            run.bytes_moved = int(payload.get("bytes_received") or 0)
        logger.info("off-site %s run %s: %s", run.action, run.id, run.status)
    db.flush()
    if copy is None:
        return
    if run.action == offsite.CHECK and run.status == offsite.OK:
        copy.lock_verified = payload.get("object_lock")
        copy.checked_at = run.finished_at
    if run.action in (offsite.CHECK, offsite.UPLOAD):
        if run.status == offsite.OK:
            copy.last_error = None
            if run.action == offsite.UPLOAD:
                copy.last_ok_at = run.finished_at
        else:
            copy.last_error = run.message or run.status


def run_view(run: models.BackupOffsiteRun) -> Dict[str, Any]:
    try:
        progress = json.loads(run.progress) if run.progress else None
    except ValueError:
        progress = None
    return {
        "id": str(run.id), "copy_id": str(run.copy_id), "host_id": str(run.host_id),
        "action": run.action, "status": run.status, "queued_at": run.queued_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "requested_by": run.requested_by, "snapshot": run.snapshot,
        "target_dataset": run.target_dataset, "bytes_moved": run.bytes_moved,
        "message": run.message, "progress": progress,
    }  # fmt: skip


def runs(db: Session, copy_id: Any, limit: int = 50) -> List[Dict[str, Any]]:
    rows = (
        db.query(models.BackupOffsiteRun)
        .filter(models.BackupOffsiteRun.copy_id == copy_id)
        .order_by(models.BackupOffsiteRun.queued_at.desc()).limit(limit).all()
    )  # fmt: skip
    return [run_view(r) for r in rows]
