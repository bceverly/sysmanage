"""Air-gap import-device endpoints (repository side).

Drive the device-based ISO import on an Air-Gap Repository:

  * GET  /api/v1/airgap/block-devices       — enumerate candidate drives
  * PUT  /api/v1/airgap/import-device        — persist the chosen drive
  * GET  /api/v1/airgap/import-device/status — is the chosen drive ready?
                                               (also the Rescan action)
  * POST /api/v1/airgap/repository/ingest-device
                                             — queue an ingest from it

All authenticated.  The Import button on the Air-Gap Repositories page
is gated on the ``status`` ``ready`` flag; pressing it calls
``ingest-device``, which inserts a QUEUED ``AirgapIngestionRun`` whose
``iso_path`` is the device node.  ``airgap_ingest_tick`` then mounts it
(read-only, no loop for a real device), verifies the signed manifest
against the trusted keyring, and copies the payload in.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services import airgap_device_service, server_config_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/airgap",
    tags=["airgap-devices"],
    dependencies=[Depends(JWTBearer())],
)


class BlockDevicesResponse(BaseModel):
    devices: list[dict]
    selected: str | None = None
    default: str | None = None


class ImportDeviceUpdate(BaseModel):
    device: str | None = None


@router.get("/block-devices", response_model=BlockDevicesResponse)
def list_block_devices():
    """List candidate import drives (OS disk excluded) + current choice."""
    devices = airgap_device_service.list_block_devices()
    return BlockDevicesResponse(
        devices=devices,
        selected=server_config_service.get_import_device(),
        default=airgap_device_service.default_device(devices),
    )


@router.put("/import-device", response_model=BlockDevicesResponse)
def set_import_device(payload: ImportDeviceUpdate):
    """Persist the chosen import drive (or null to clear).

    Validates the device is one of the enumerated candidates (so a typo
    or the OS disk can't be set), unless clearing.
    """
    device = payload.device
    if device:
        paths = {d["path"] for d in airgap_device_service.list_block_devices()}
        if device not in paths:
            raise HTTPException(
                status_code=400,
                detail=_("Device %s is not an available import drive") % device,
            )
    server_config_service.set_import_device(device)
    devices = airgap_device_service.list_block_devices()
    return BlockDevicesResponse(
        devices=devices,
        selected=device,
        default=airgap_device_service.default_device(devices),
    )


@router.get("/import-device/status")
def import_device_status():
    """Probe the selected drive (the Rescan action).

    Returns ``{device, ready, reason, label?, fstype?}``.  ``ready``
    True means it carries an ISO filesystem and the Import button can be
    enabled; the collector-signature check is enforced at ingest time.
    """
    selected = server_config_service.get_import_device()
    if not selected:
        return {
            "device": None,
            "ready": False,
            "reason": _("no import device selected"),
        }
    return airgap_device_service.probe_device(selected)


class IngestDeviceResponse(BaseModel):
    run_id: str
    device: str


@router.post("/repository/ingest-device", response_model=IngestDeviceResponse)
def ingest_from_device(db: Session = Depends(get_db)):
    """Queue an ingest from the selected import drive.

    Requires a device to be selected AND to currently look like ISO
    media (``status.ready``).  Inserts a QUEUED ``AirgapIngestionRun``
    pointing at the device node; the ingest tick drives it forward.
    """
    selected = server_config_service.get_import_device()
    if not selected:
        raise HTTPException(status_code=409, detail=_("No import device selected"))
    status = airgap_device_service.probe_device(selected)
    if not status.get("ready"):
        raise HTTPException(
            status_code=409,
            detail=_("Import device not ready: %s") % status.get("reason", "unknown"),
        )
    run = models.AirgapIngestionRun(iso_path=selected, status="QUEUED")
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info("Queued device ingest run %s from %s", run.id, selected)
    return IngestDeviceResponse(run_id=str(run.id), device=selected)


class IngestRun(BaseModel):
    id: str
    status: str
    error_message: str | None = None
    file_count: int | None = None
    byte_count: int | None = None
    iso_path: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class IngestRunList(BaseModel):
    runs: list[IngestRun]


@router.get("/repository/ingest-runs", response_model=IngestRunList)
def list_ingest_runs(limit: int = 10, db: Session = Depends(get_db)):
    """Recent ingestion runs (newest first) for the Import panel to poll.

    Lets the UI show an in-flight import advancing
    (QUEUED → VERIFYING_SIG → COPYING → COMPLETE) and refresh the
    repository list when a run finishes, instead of requiring a manual
    page reload.
    """
    limit = max(1, min(limit, 50))
    rows = (
        db.query(models.AirgapIngestionRun)
        .order_by(models.AirgapIngestionRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return IngestRunList(
        runs=[
            IngestRun(
                id=str(r.id),
                status=r.status,
                error_message=r.error_message,
                file_count=r.file_count,
                byte_count=r.byte_count,
                iso_path=r.iso_path,
                started_at=r.started_at.isoformat() if r.started_at else None,
                completed_at=r.completed_at.isoformat() if r.completed_at else None,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in rows
        ]
    )
