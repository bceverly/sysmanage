# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
This module houses the API routes for Ubuntu Pro settings management in SysManage.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services.audit_service import AuditService, EntityType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

router = APIRouter()
queue_ops = QueueOperations()


class UbuntuProSettingsResponse(BaseModel):
    """Response model for Ubuntu Pro settings."""

    id: str
    master_key: Optional[str] = None
    organization_name: Optional[str] = None
    auto_attach_enabled: bool = False
    created_at: datetime
    updated_at: datetime

    @validator("id", pre=True)
    def convert_uuid_to_string(
        cls, value
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class UbuntuProSettingsUpdate(BaseModel):
    """Request model for updating Ubuntu Pro settings."""

    master_key: Optional[str] = None
    organization_name: Optional[str] = None
    auto_attach_enabled: Optional[bool] = None

    @validator("master_key")
    def validate_master_key(
        cls, master_key
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
        """Validate the master key format if provided."""
        if master_key is not None and master_key.strip() == "":
            return None
        if master_key is not None:
            # Basic validation - should start with 'C' for contract-based keys
            if not master_key.startswith("C"):
                raise ValueError(
                    _("Ubuntu Pro key must start with 'C' for contract-based keys")
                )
            # Key should be at least 24 characters long
            if len(master_key) < 24:
                raise ValueError(_("Ubuntu Pro key appears to be too short"))
        return master_key

    @validator("organization_name")
    def validate_organization_name(
        cls, organization_name
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
        """Validate organization name."""
        if organization_name is not None and organization_name.strip() == "":
            return None
        if organization_name is not None and len(organization_name) > 255:
            raise ValueError(_("Organization name must be 255 characters or less"))
        return organization_name


@router.get("/", response_model=UbuntuProSettingsResponse)
async def get_ubuntu_pro_settings(
    db: Session = Depends(get_tenant_db), dependencies=Depends(JWTBearer())
):
    """Get current Ubuntu Pro settings."""
    try:
        # Phase 13.1: the Ubuntu Pro settings record is tenant-scoped, so the
        # "get-or-create singleton" now routes to the active tenant's database
        # via ``get_tenant_db`` — each tenant gets its own singleton (intended).
        # Inert in collapsed/single-tenant mode (same engine as get_db).
        # Get or create the singleton settings record
        settings = db.query(models.UbuntuProSettings).first()

        if not settings:
            # Create default settings if they don't exist
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            settings = models.UbuntuProSettings(
                auto_attach_enabled=False,
                created_at=now,
                updated_at=now,
            )
            db.add(settings)
            db.commit()

        return settings

    except Exception as e:
        logger.exception("Error getting Ubuntu Pro settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve Ubuntu Pro settings: %s") % str(e),
        ) from e


@router.put("/", response_model=UbuntuProSettingsResponse)
async def update_ubuntu_pro_settings(
    settings_update: UbuntuProSettingsUpdate,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Update Ubuntu Pro settings."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the settings data routes to the tenant engine via db_session.
    if not current_user.has_role(SecurityRoles.CHANGE_UBUNTU_PRO_MASTER_KEY):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: CHANGE_UBUNTU_PRO_MASTER_KEY role required"),
        )
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    try:
        # Get or create the singleton settings record
        settings = db_session.query(models.UbuntuProSettings).first()

        if not settings:
            # Create new settings record
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            settings = models.UbuntuProSettings(
                master_key=settings_update.master_key,
                organization_name=settings_update.organization_name,
                auto_attach_enabled=settings_update.auto_attach_enabled or False,
                created_at=now,
                updated_at=now,
            )
            db_session.add(settings)
        else:
            # Update existing settings
            # Note: master_key can be None (to clear it), so we check if it was provided in the request
            if (
                hasattr(settings_update, "master_key")
                and "master_key" in settings_update.__fields_set__
            ):
                settings.master_key = settings_update.master_key
            if settings_update.organization_name is not None:
                settings.organization_name = settings_update.organization_name
            if settings_update.auto_attach_enabled is not None:
                settings.auto_attach_enabled = settings_update.auto_attach_enabled

            settings.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        db_session.commit()
        db_session.refresh(settings)

        logger.info(
            "Ubuntu Pro settings updated: organization=%s, has_master_key=%s, auto_attach=%s",
            sanitize_log(settings.organization_name),
            settings.master_key is not None,
            sanitize_log(settings.auto_attach_enabled),
        )

        # Log audit entry for settings update on the MAIN engine (audit trail
        # is server-global).
        with session_local() as audit_session:
            AuditService.log_update(
                db=audit_session,
                entity_type=EntityType.SETTING,
                entity_name="Ubuntu Pro Settings",
                user_id=current_user.id,
                username=current_user.userid,
                entity_id=str(settings.id),
                details={
                    "organization_name": settings.organization_name,
                    "has_master_key": settings.master_key is not None,
                    "auto_attach_enabled": settings.auto_attach_enabled,
                },
            )

        return settings

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Error updating Ubuntu Pro settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to update Ubuntu Pro settings: %s") % str(e),
        ) from e


@router.delete("/master-key")
async def clear_master_key(
    db: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Clear the stored Ubuntu Pro master key."""
    # Authorization/identity is resolved on the MAIN engine by
    # require_authenticated_user (user data is server-global); the audit trail
    # also stays on the main engine, while the settings data routes to the
    # tenant engine via db.
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    try:
        settings = db.query(models.UbuntuProSettings).first()

        if settings:
            settings.master_key = None
            settings.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()

            logger.info("Ubuntu Pro master key cleared")

            # Log audit entry for master key deletion on the MAIN engine.
            with session_local() as audit_session:
                AuditService.log_delete(
                    db=audit_session,
                    entity_type=EntityType.SETTING,
                    entity_name="Ubuntu Pro Master Key",
                    user_id=current_user.id,
                    username=current_user.userid,
                    entity_id=str(settings.id),
                )

            return {"message": _("Master key cleared successfully")}

        return {"message": _("No settings found to clear")}

    except Exception as e:
        logger.exception("Error clearing Ubuntu Pro master key: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to clear master key: %s") % str(e),
        ) from e


@router.get("/master-key/status")
async def get_master_key_status(
    db: Session = Depends(get_tenant_db), dependencies=Depends(JWTBearer())
):
    """Get the status of the master key (exists or not) without exposing the key."""
    try:
        settings = db.query(models.UbuntuProSettings).first()

        has_master_key = settings is not None and settings.master_key is not None
        organization_name = settings.organization_name if settings else None

        return {
            "has_master_key": has_master_key,
            "organization_name": organization_name,
            "auto_attach_enabled": (
                settings.auto_attach_enabled if settings else False
            ),
        }

    except Exception as e:
        logger.exception("Error getting master key status: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to get master key status: %s") % str(e),
        ) from e


class UbuntuProEnrollmentRequest(BaseModel):
    """Request model for Ubuntu Pro enrollment."""

    host_ids: list[str]
    use_master_key: bool = True
    custom_key: Optional[str] = None

    @validator("host_ids")
    def validate_host_ids(
        cls, host_ids
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
        """Validate host IDs list."""
        if not host_ids:
            raise ValueError(_("At least one host must be specified"))
        return host_ids

    @validator("custom_key")
    def validate_custom_key(
        cls, custom_key, values
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
        """Validate custom key if not using master key."""
        if not values.get("use_master_key", True) and not custom_key:
            raise ValueError(_("Custom key must be provided when not using master key"))
        if custom_key and not custom_key.startswith("C"):
            raise ValueError(
                _("Ubuntu Pro key must start with 'C' for contract-based keys")
            )
        return custom_key


@router.post("/enroll")
async def enroll_hosts_in_ubuntu_pro(
    request: UbuntuProEnrollmentRequest,
    db: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
):
    """Enroll specified hosts in Ubuntu Pro using master key or custom key."""
    try:
        from backend.websocket.messages import create_command_message

        # Validate request: if not using master key, custom key must be provided
        if not request.use_master_key and not request.custom_key:
            raise HTTPException(
                status_code=422,
                detail=_("Custom key must be provided when not using master key"),
            )

        # Get the key to use for enrollment
        enrollment_key = None

        if request.use_master_key:
            settings = db.query(models.UbuntuProSettings).first()

            if not settings or not settings.master_key:
                raise HTTPException(
                    status_code=400,
                    detail=_(
                        "No master key configured. Please configure a master key first."
                    ),
                )
            enrollment_key = settings.master_key
        else:
            enrollment_key = request.custom_key

        results = []

        # Bulk-fetch active hosts in one query rather than per-id
        # ``.first()`` (flagged in the Phase 6 N+1 audit).  Key by
        # str(id) so string host_ids from the request payload match
        # the GUID column.
        active_hosts_by_id = {
            str(h.id): h
            for h in db.query(models.Host)
            .filter(
                models.Host.id.in_(request.host_ids),
                models.Host.active.is_(True),
            )
            .all()
        }

        for host_id in request.host_ids:
            host = active_hosts_by_id.get(str(host_id))

            if not host:
                results.append(
                    {
                        "host_id": host_id,
                        "success": False,
                        "error": _("Host not found or inactive"),
                    }
                )
                continue

            try:
                # Send Ubuntu Pro enrollment command to agent
                command_message = create_command_message(
                    "ubuntu_pro_attach",
                    {
                        "token": enrollment_key,
                        "organization": request.use_master_key
                        and settings
                        and settings.organization_name,
                    },
                )

                queue_ops.enqueue_message(
                    message_type="command",
                    message_data=command_message,
                    direction=QueueDirection.OUTBOUND,
                    host_id=host.id,
                    db=db,
                )

                results.append(
                    {
                        "host_id": host_id,
                        "hostname": host.fqdn,
                        "success": True,
                        "message": _("Ubuntu Pro enrollment initiated"),
                    }
                )

            except (ConnectionError, ValueError, RuntimeError) as e:
                results.append(
                    {
                        "host_id": host_id,
                        "hostname": host.fqdn,
                        "success": False,
                        "error": _("Failed to send enrollment command: %s") % str(e),
                    }
                )

        # Commit the session to persist all queued messages
        db.commit()

        return {"results": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error enrolling hosts in Ubuntu Pro: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to initiate Ubuntu Pro enrollment: %s") % str(e),
        ) from e
