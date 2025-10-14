"""API routes for receiving update reports from agents."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import db, models

from .models import UpdatesReport

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/report/{host_id}")
async def report_updates(
    host_id: str, updates_report: UpdatesReport, dependencies=Depends(JWTBearer())
):
    """Receive and store update information from agents."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Verify host exists
            host = session.query(models.Host).filter(models.Host.id == host_id).first()
            if not host:
                raise HTTPException(status_code=404, detail=_("Host not found"))

            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Clear existing updates for this host
            session.query(models.PackageUpdate).filter(
                models.PackageUpdate.host_id == host_id
            ).delete()

            for update_info in updates_report.available_updates:
                update_type = "package"
                if update_info.is_security_update:
                    update_type = "security"
                elif update_info.is_system_update:
                    update_type = "system"

                package_update = models.PackageUpdate(
                    host_id=host_id,
                    package_name=update_info.package_name,
                    current_version=update_info.current_version or "unknown",
                    available_version=update_info.available_version,
                    package_manager=update_info.package_manager,
                    update_type=update_type,
                    priority=None,
                    description=None,
                    size_bytes=update_info.update_size_bytes,
                    requires_reboot=update_info.requires_reboot,
                    discovered_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(package_update)

            session.commit()
            return {
                "status": "success",
                "updates_stored": len(updates_report.available_updates),
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to store updates: %s") % str(e)
        ) from e
