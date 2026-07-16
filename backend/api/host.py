# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
This module houses the API routes for the host object in SysManage.
"""

# host.py is the host-API aggregator; it is intentionally large (mirrors the
# pattern in proplus_routes / repository_mirroring).
# pylint: disable=too-many-lines

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

# Import the new router modules
from backend.api import (
    host_account_management,
    host_approval,
    host_data_updates,
    host_graylog,
    host_monitoring,
    host_operations,
    host_ubuntu_pro,
    host_utils,
)
from backend.api.error_constants import error_host_not_found, error_user_not_found
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import sanitize_log
from backend.websocket.queue_operations import QueueOperations

# Split into separate routers for different authentication requirements
public_router = APIRouter()  # Unauthenticated endpoints (no /api prefix)
auth_router = APIRouter()  # Authenticated endpoints (with /api prefix)

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()

# Backward compatibility - this allows existing imports to still work
router = public_router  # Default to public router for backward compatibility


class HostRegistration(BaseModel):
    """
    This class represents the minimal JSON payload for agent registration.
    Only contains essential connection information.
    """

    class Config:
        extra = "forbid"  # Forbid extra fields to enforce data separation

    # Message envelope fields (sent by agent, not stored)
    message_type: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: Optional[str] = None

    # Registration data
    active: bool
    fqdn: str
    hostname: str
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    script_execution_enabled: Optional[bool] = None
    is_privileged: Optional[bool] = None
    enabled_shells: Optional[List[str]] = None
    agent_version: Optional[str] = None
    auto_approve_token: Optional[str] = None
    # Phase 8.1: optional pre-shared registration key.  When supplied
    # and valid, the server enrolls the host into the key's
    # access_group and (if the key has auto_approve=True) skips the
    # manual approval gate.
    registration_key: Optional[str] = None
    # Phase 13.1: optional tenant enrollment token.  When supplied and valid,
    # binds the host to the token's tenant (host→tenant index) so the data
    # plane routes this host's data to that tenant's database.
    enrollment_token: Optional[str] = None


class HostRegistrationLegacy(BaseModel):
    """
    Legacy registration model for backward compatibility.
    Contains all fields for comprehensive registration.
    """

    active: bool
    fqdn: str
    hostname: str
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    platform: Optional[str] = None
    platform_release: Optional[str] = None
    platform_version: Optional[str] = None
    architecture: Optional[str] = None
    processor: Optional[str] = None
    machine_architecture: Optional[str] = None
    python_version: Optional[str] = None
    os_info: Optional[Dict[str, Any]] = None


class Host(BaseModel):
    """
    This class represents the JSON payload to the /host POST/PUT requests.
    """

    active: bool
    fqdn: str
    ipv4: str
    ipv6: str


@auth_router.delete("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def delete_host(host_id: str, current_user: str = Depends(get_current_user)):
    """
    This function deletes a single host given an id
    """

    from backend.persistence.partitions import request_sessionmaker  # noqa: PLC0415

    # Authorization on the MAIN engine — users/roles are server-global.
    auth_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )
    with auth_local() as auth_session:
        user = (
            auth_session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=error_user_not_found())
        if user._role_cache is None:
            user.load_role_cache(auth_session)
        if not user.has_role(SecurityRoles.DELETE_HOST):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DELETE_HOST role required"),
            )
        # Capture before the auth session closes — used for the audit below.
        user_id = user.id

    # Host data lives in the active tenant's database (Phase 13.1); a bound host
    # isn't in the bootstrap DB, so route the delete to the request's tenant —
    # the same database get_host reads it from.
    session_local = request_sessionmaker()
    with session_local() as session:
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail=error_host_not_found())

        # Extract values before deletion to avoid ObjectDeletedError
        deleted_fqdn = hosts[0].fqdn

        session.query(models.Host).filter(models.Host.id == host_id).delete()
        session.commit()

    # Phase 13.1: drop the host→tenant index binding so no stale row lingers
    # (background dispatch would otherwise keep routing a now-deleted host).
    # Inert (no-op) in single-tenant mode / when the licensed engine isn't loaded.
    from backend.services import host_tenant_index  # noqa: PLC0415

    host_tenant_index.unbind_host(host_id)

    # Audit on the MAIN engine — the audit trail is server-global.
    audit_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with audit_local() as audit_session:
        AuditService.log_delete(
            db=audit_session,
            user_id=user_id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=deleted_fqdn,
        )

    return {"result": True}


@auth_router.get("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def get_host(host_id: str, current_user: str = Depends(get_current_user)):
    """
    This function retrieves a single host by its id
    """
    from backend.persistence.partitions import request_sessionmaker  # noqa: PLC0415

    # Authorization on the MAIN engine — users/roles are server-global.
    auth_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with auth_local() as auth_session:
        user = (
            auth_session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=error_user_not_found())
        if user._role_cache is None:
            user.load_role_cache(auth_session)
        if not user.has_role(SecurityRoles.VIEW_HOST_DETAILS):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: VIEW_HOST_DETAILS role required"),
            )

    # Host data lives in the active tenant's database (Phase 13.1); a bound host
    # isn't in the bootstrap DB, so route the host query to the request's tenant.
    session_local = request_sessionmaker()
    with session_local() as session:
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=error_host_not_found())

        # Get tags using the dynamic relationship
        host_tags = host.tags.all()

        # Calculate update counts from package_updates relationship
        package_updates = host.package_updates
        security_updates_count = sum(
            1
            for update in package_updates
            if getattr(update, "is_security_update", False)
        )
        system_updates_count = sum(
            1
            for update in package_updates
            if getattr(update, "is_system_update", False)
        )
        total_updates_count = len(package_updates)

        # Return as dictionary with all fields
        return {
            "id": str(host.id),
            "active": host.active,
            "fqdn": host.fqdn,
            "ipv4": host.ipv4,
            "ipv6": host.ipv6,
            "last_access": (
                host.last_access.replace(tzinfo=timezone.utc).isoformat()
                if host.last_access
                else None
            ),
            "status": host.status,
            "approval_status": host.approval_status,
            "platform": host.platform,
            "platform_release": host.platform_release,
            "platform_version": host.platform_version,
            "machine_architecture": host.machine_architecture,
            "processor": host.processor,
            "timezone": getattr(host, "timezone", None),
            "cpu_vendor": host.cpu_vendor,
            "cpu_model": host.cpu_model,
            "cpu_cores": host.cpu_cores,
            "cpu_threads": host.cpu_threads,
            "cpu_frequency_mhz": host.cpu_frequency_mhz,
            "memory_total_mb": host.memory_total_mb,
            "reboot_required": host.reboot_required,
            "is_agent_privileged": host.is_agent_privileged,
            "agent_version": host.agent_version,
            "script_execution_enabled": getattr(
                host, "script_execution_enabled", False
            ),
            "enabled_shells": getattr(host, "enabled_shells", None),
            # Include parent host ID for child host filtering
            "parent_host_id": (
                str(getattr(host, "parent_host_id", None))
                if getattr(host, "parent_host_id", None)
                else None
            ),
            # Include update counts
            "security_updates_count": security_updates_count,
            "system_updates_count": system_updates_count,
            "total_updates_count": total_updates_count,
            # Include tags
            "tags": [
                {"id": str(tag.id), "name": tag.name, "description": tag.description}
                for tag in host_tags
            ],
            # Phase 12.7: agent-reported public IP + geo resolution
            "public_ip": host.public_ip,
            "public_ip_resolved_at": (
                host.public_ip_resolved_at.replace(tzinfo=timezone.utc).isoformat()
                if host.public_ip_resolved_at
                else None
            ),
            "geo_country_code": host.geo_country_code,
            "geo_subdivision_code": host.geo_subdivision_code,
            "geo_city": host.geo_city,
            "geo_latitude": host.geo_latitude,
            "geo_longitude": host.geo_longitude,
        }


@auth_router.get("/host/by_fqdn/{fqdn}", dependencies=[Depends(JWTBearer())])
async def get_host_by_fqdn_endpoint(fqdn: str):
    """
    This function retrieves a single host by fully qualified domain name
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        host = session.query(models.Host).filter(models.Host.fqdn == fqdn).first()
        if not host:
            raise HTTPException(status_code=404, detail=error_host_not_found())

        # Get tags using the dynamic relationship
        host_tags = host.tags.all()

        # Calculate update counts from package_updates relationship
        package_updates = host.package_updates
        security_updates_count = sum(
            1
            for update in package_updates
            if getattr(update, "is_security_update", False)
        )
        system_updates_count = sum(
            1
            for update in package_updates
            if getattr(update, "is_system_update", False)
        )
        total_updates_count = len(package_updates)

        # Return as dictionary with all fields
        return {
            "id": str(host.id),
            "active": host.active,
            "fqdn": host.fqdn,
            "ipv4": host.ipv4,
            "ipv6": host.ipv6,
            "last_access": (
                host.last_access.replace(tzinfo=timezone.utc).isoformat()
                if host.last_access
                else None
            ),
            "status": host.status,
            "approval_status": host.approval_status,
            "platform": host.platform,
            "platform_release": host.platform_release,
            "platform_version": host.platform_version,
            "machine_architecture": host.machine_architecture,
            "processor": host.processor,
            "timezone": getattr(host, "timezone", None),
            "cpu_vendor": host.cpu_vendor,
            "cpu_model": host.cpu_model,
            "cpu_cores": host.cpu_cores,
            "cpu_threads": host.cpu_threads,
            "cpu_frequency_mhz": host.cpu_frequency_mhz,
            "memory_total_mb": host.memory_total_mb,
            "reboot_required": host.reboot_required,
            "is_agent_privileged": host.is_agent_privileged,
            "agent_version": host.agent_version,
            "script_execution_enabled": getattr(
                host, "script_execution_enabled", False
            ),
            "enabled_shells": getattr(host, "enabled_shells", None),
            # Include update counts
            "security_updates_count": security_updates_count,
            "system_updates_count": system_updates_count,
            "total_updates_count": total_updates_count,
            # Include tags
            "tags": [
                {"id": str(tag.id), "name": tag.name, "description": tag.description}
                for tag in host_tags
            ],
        }


def _get_all_hosts_sync(tenant_id=None):
    """
    Synchronous helper function to retrieve all hosts.
    This runs in a thread pool to avoid blocking the event loop.

    Phase 13.1: routes to the active tenant's database when multi-tenancy is
    enabled.  ``tenant_id`` is captured by the async caller and passed in
    because the active-tenant ContextVar does not cross the thread-pool
    boundary.  In single-tenant / server scope this is the main engine.
    """
    from backend.persistence.partitions import get_request_engine  # noqa: PLC0415

    # Server scope (no active tenant) uses the module-local ``db.get_engine()``
    # directly — identical to before, and it keeps the existing unit tests that
    # mock ``host.db`` working.  Only when a tenant is actually in scope do we
    # route through the seam to that tenant's engine.  Keep the module-local
    # ``sessionmaker`` so only the bound engine changes.
    bind = db.get_engine() if tenant_id is None else get_request_engine(tenant_id)
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=bind
    )

    with session_local() as session:
        hosts = session.query(models.Host).all()

        # Bulk-fetch the host→tag mapping in one query rather than
        # ``host.tags.all()`` per host (the dynamic relationship issued
        # 1+N queries — flagged in the Phase 6 N+1 audit).
        host_ids = [h.id for h in hosts]
        tags_by_host: dict = {}
        if host_ids:
            tag_rows = (
                session.query(models.HostTag.host_id, models.Tag)
                .join(models.Tag, models.Tag.id == models.HostTag.tag_id)
                .filter(models.HostTag.host_id.in_(host_ids))
                .all()
            )
            for hid, tag in tag_rows:
                tags_by_host.setdefault(hid, []).append(tag)

        # Convert to dictionaries with tags included
        result = []
        for host in hosts:
            host_tags = tags_by_host.get(host.id, [])

            # Calculate update counts from package_updates relationship
            package_updates = host.package_updates
            security_updates_count = sum(
                1
                for update in package_updates
                if getattr(update, "is_security_update", False)
            )
            system_updates_count = sum(
                1
                for update in package_updates
                if getattr(update, "is_system_update", False)
            )
            total_updates_count = len(package_updates)

            host_dict = {
                "id": str(host.id),
                "active": host.active,
                "fqdn": host.fqdn,
                "ipv4": host.ipv4,
                "ipv6": host.ipv6,
                "last_access": (
                    host.last_access.replace(tzinfo=timezone.utc).isoformat()
                    if host.last_access
                    else None
                ),
                "status": host.status,
                "approval_status": host.approval_status,
                "platform": host.platform,
                "platform_release": host.platform_release,
                "platform_version": host.platform_version,
                "machine_architecture": host.machine_architecture,
                "processor": host.processor,
                "cpu_vendor": host.cpu_vendor,
                "cpu_model": host.cpu_model,
                "cpu_cores": host.cpu_cores,
                "cpu_threads": host.cpu_threads,
                "cpu_frequency_mhz": host.cpu_frequency_mhz,
                "memory_total_mb": host.memory_total_mb,
                "reboot_required": host.reboot_required,
                "is_agent_privileged": host.is_agent_privileged,
                "agent_version": host.agent_version,
                "script_execution_enabled": getattr(
                    host, "script_execution_enabled", False
                ),
                "enabled_shells": getattr(host, "enabled_shells", None),
                # Include parent host ID for child host filtering
                "parent_host_id": (
                    str(getattr(host, "parent_host_id", None))
                    if getattr(host, "parent_host_id", None)
                    else None
                ),
                # Include update counts
                "security_updates_count": security_updates_count,
                "system_updates_count": system_updates_count,
                "total_updates_count": total_updates_count,
                # Include tags
                "tags": [
                    {
                        "id": str(tag.id),
                        "name": tag.name,
                        "description": tag.description,
                    }
                    for tag in host_tags
                ],
                # Include virtualization support info
                "virtualization_types": host.virtualization_types,
                "virtualization_capabilities": host.virtualization_capabilities,
            }
            result.append(host_dict)

        return result


@auth_router.get("/hosts", dependencies=[Depends(JWTBearer())])
async def get_all_hosts():
    """
    This function retrieves all hosts in the system.
    Runs the database query in a thread pool to avoid blocking the event loop.
    """
    # Capture the active tenant HERE, in the request's async context — the
    # ContextVar won't be visible inside the thread-pool worker below.
    from backend.persistence.tenant_context import get_active_tenant

    tenant_id = get_active_tenant()
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_all_hosts_sync, tenant_id)


def _get_host_geolocations_sync():
    """
    Phase 12.7: return geo-locatable hosts for the world-map UI.

    Filters to rows where ``geo_latitude`` and ``geo_longitude`` are
    both populated — hosts that haven't been resolved yet (or whose
    public IP is internal-only / airgapped) are excluded.  The map
    component doesn't try to plot "unknown location" markers; those
    hosts simply don't appear until their next heartbeat resolves.

    Honours the privacy opt-out tag: a host tagged ``no_geo_track``
    is excluded from the result via a NOT EXISTS subquery against the
    host_tags / tags join.  Subquery form keeps the filter portable
    across SQLite (no LATERAL) and PostgreSQL.

    Returned shape mirrors what the frontend MapView actually consumes:
    just the fields needed for marker placement + popup metadata, not
    the full Host row.  Keeps the response under a few hundred KB even
    at 10k-host scale.
    """
    from backend.services.geolocation_service import NO_GEO_TRACK_TAG

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )
    with session_local() as session:
        # NOT EXISTS subquery: exclude hosts where any tag with
        # name = NO_GEO_TRACK_TAG is linked to the host via host_tags.
        opt_out_exists = (
            session.query(models.HostTag.id)
            .join(models.Tag, models.HostTag.tag_id == models.Tag.id)
            .filter(
                models.HostTag.host_id == models.Host.id,
                models.Tag.name == NO_GEO_TRACK_TAG,
            )
            .exists()
        )
        rows = (
            session.query(models.Host)
            .filter(
                models.Host.geo_latitude.isnot(None),
                models.Host.geo_longitude.isnot(None),
                models.Host.active.is_(True),
                ~opt_out_exists,
            )
            .all()
        )
        return [
            {
                "host_id": str(host.id),
                "fqdn": host.fqdn,
                "status": host.status,
                "platform": host.platform,
                "country_code": host.geo_country_code,
                "subdivision_code": host.geo_subdivision_code,
                "city": host.geo_city,
                "latitude": host.geo_latitude,
                "longitude": host.geo_longitude,
            }
            for host in rows
        ]


@auth_router.get("/hosts/geolocations", dependencies=[Depends(JWTBearer())])
async def get_host_geolocations():
    """Return geo-located hosts for the world-map visualization (Phase 12.7)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_host_geolocations_sync)


@auth_router.post("/host", dependencies=[Depends(JWTBearer())])
async def add_host(new_host: Host, current_user: str = Depends(get_current_user)):
    """
    This function adds a new host to the system.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Add the data to the database
    with session_local() as session:
        # Get the user object for audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=error_user_not_found())
        # See if we are trying to add a duplicate host
        check_duplicate = (
            session.query(models.Host).filter(models.Host.fqdn == new_host.fqdn).all()
        )
        if len(check_duplicate) > 0:
            raise HTTPException(status_code=409, detail=_("Host already exists"))

        # Host doesn't exist so proceed with adding it
        host = models.Host(
            fqdn=new_host.fqdn,
            active=new_host.active,
            ipv4=new_host.ipv4,
            ipv6=new_host.ipv6,
            last_access=datetime.now(timezone.utc),
        )
        host.approval_status = "approved"  # Manually created hosts are pre-approved
        session.add(host)
        session.commit()
        session.refresh(host)

        # Audit log host creation
        AuditService.log_create(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            details={
                "active": new_host.active,
                "ipv4": new_host.ipv4,
                "ipv6": new_host.ipv6,
            },
        )

        # Return dictionary to avoid detached object issues
        return {
            "id": str(host.id),
            "active": host.active,
            "fqdn": host.fqdn,
            "ipv4": host.ipv4,
            "ipv6": host.ipv6,
            "last_access": (
                host.last_access.replace(tzinfo=timezone.utc).isoformat()
                if host.last_access
                else None
            ),
            "status": host.status,
            "approval_status": host.approval_status,
        }


def _refresh_existing_host(session, existing_host, registration_data) -> "models.Host":
    """Update an already-registered host's network/active fields from a
    re-registration payload.  Script-execution capability is intentionally
    NOT touched — that's an admin-configured server-side setting."""
    print("Updating existing host with minimal registration data...")
    try:
        existing_host.active = registration_data.active
        existing_host.ipv4 = registration_data.ipv4
        existing_host.ipv6 = registration_data.ipv6
        existing_host.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
        print(
            f"Before commit - FQDN: {existing_host.fqdn}, Active: {existing_host.active}"
        )
        session.commit()
        print("Database commit successful")
        session.refresh(existing_host)
        print("After refresh - Host updated with minimal data")
        return existing_host
    except Exception as e:
        print(f"Error updating existing host: {e}")
        session.rollback()
        raise


def _validate_registration_key(session, raw_key):
    """Resolve a registration key string to a usable ``RegistrationKey``
    row.  Returns the row when valid, ``None`` when no key was supplied,
    raises 403 otherwise.  We deliberately don't leak which condition
    (revoked/expired/max-uses) failed."""
    if not raw_key:
        return None
    validated_key = (
        session.query(models.RegistrationKey)
        .filter(models.RegistrationKey.key == raw_key)
        .first()
    )
    if validated_key is None or not validated_key.is_usable():
        raise HTTPException(
            status_code=403,
            detail=_("Invalid or expired registration key"),
        )
    return validated_key


def _resolve_enrollment_tenant(raw_token):
    """Validate + consume a tenant enrollment token; return its tenant id.

    Returns ``None`` when multi-tenancy is DISABLED or no token was supplied — a
    token-less registration is still a legitimate server-scoped ("No tenant")
    host while that concept exists.  Raises 403 for a supplied-but-invalid token
    (unknown / revoked / expired / out of uses).  Consumes one use on success
    (bumps use_count / last_used_at).

    A MISSING token is NOT rejected here: the phantom-duplicate loophole is
    closed narrowly in ``register_host`` via ``_reject_if_fqdn_belongs_to_tenant``
    (which only fails a token-less registration when the fqdn already lives in a
    tenant DB), so ordinary server-scoped registration keeps working.
    """
    from backend.config import config as _config  # noqa: PLC0415

    if not raw_token:
        return None

    if not _config.is_multitenancy_enabled():
        return None

    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )
    from backend.services import enrollment_service  # noqa: PLC0415

    with partition_session(partition=PARTITION_REGISTRY) as session:
        tenant_id = enrollment_service.validate_and_consume(session, raw_token)
    if tenant_id is None:
        raise HTTPException(
            status_code=403, detail=_("Invalid or expired enrollment token")
        )
    return tenant_id


def _reject_if_fqdn_belongs_to_tenant(fqdn):
    """Close the phantom-duplicate loophole for a token-less registration.

    A registration with no enrollment token writes to the no-tenant/bootstrap
    database.  Dedup is per-partition (there is no cross-partition lookup), so if
    this ``fqdn`` already lives in a TENANT database, creating a server-scoped row
    here would be a cross-partition PHANTOM of a host that belongs to a tenant —
    exactly the ghost-row bug we chased.  Reject loudly (403) so the agent
    surfaces its missing/bad tenant binding and re-enrolls with its token instead
    of accreting a duplicate.  No-op when multi-tenancy is off (no tenant DBs to
    collide with) or the fqdn is genuinely new.
    """
    from backend.config import config as _config  # noqa: PLC0415

    if not _config.is_multitenancy_enabled():
        return

    from backend.websocket.inbound_processor import (  # noqa: PLC0415
        _find_host_in_tenant_dbs,
    )

    host, tenant_session = _find_host_in_tenant_dbs(None, fqdn)
    if host is None:
        return
    try:
        owner_fqdn = host.fqdn
    finally:
        tenant_session.close()

    # False positive: the only logged value is a sanitized FQDN (a hostname);
    # the word "token" appears solely in the static advice text, not as a
    # secret. See sanitize_log() and owner_fqdn = host.fqdn above.
    logger.warning(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        "Rejected token-less registration for fqdn=%s: it already belongs to a "
        "tenant database — a server-scoped row would be a phantom duplicate. The "
        "agent must re-register with its enrollment token.",
        sanitize_log(owner_fqdn),
    )
    raise HTTPException(
        status_code=403,
        detail=_(
            "This host already belongs to a tenant. Re-register with its "
            "enrollment token instead of registering server-scoped."
        ),
    )


def _host_write_engine(enrollment_tenant_id):
    """The engine the new host row (and its tenant-scoped enrollment side-effects)
    is created on: the enrolling tenant's database when a token resolved a tenant,
    otherwise the bootstrap engine.  Extracted from ``register_host`` to keep its
    cognitive complexity under the cap."""
    if enrollment_tenant_id is None:
        return db.get_engine()
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_TENANT,
        resolve_engine,
    )

    return resolve_engine(partition=PARTITION_TENANT, tenant_id=enrollment_tenant_id)


def _apply_registration_key_enrollment(session, host, validated_key):
    """Phase 8.1: enroll the host into the matched key's access group and bump the
    key's ``use_count`` / ``last_used_at``.  No-op when no key matched.  Extracted
    from ``register_host`` to keep its cognitive complexity under the cap; the
    caller commits so "use_count reflects successful enrollments" stays atomic."""
    if validated_key is None:
        return
    if validated_key.access_group_id is not None:
        session.add(
            models.HostAccessGroup(
                host_id=host.id,
                access_group_id=validated_key.access_group_id,
            )
        )
    validated_key.use_count = (validated_key.use_count or 0) + 1
    validated_key.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)


@public_router.post("/host/register")
async def register_host(registration_data: HostRegistration):
    """
    Register a new host (agent) with the system.
    This endpoint does not require authentication for initial registration.
    """
    # Phase 13.1: resolve the enrollment token BEFORE opening the host session —
    # it both rejects a bad registration (403) and selects which database the
    # host lives in.  None when MT is off / no token → server-scoped (bootstrap).
    # A token is consumed even if the host already exists in the target tenant DB.
    enrollment_tenant_id = _resolve_enrollment_tenant(
        registration_data.enrollment_token
    )

    # host + access-group join + reg-key bump + audit are all tenant-scoped
    # (unprefixed) tables → one database: the enrolling tenant's when a token
    # resolved a tenant (so the per-tenant queue processor finds the host and
    # doesn't delete its messages), else bootstrap.  See ``_host_write_engine``.
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False,
        autoflush=False,
        bind=_host_write_engine(enrollment_tenant_id),
    )

    with session_local() as session:
        existing_host = (
            session.query(models.Host)
            .filter(models.Host.fqdn == registration_data.fqdn)
            .first()
        )
        if existing_host:
            return _refresh_existing_host(session, existing_host, registration_data)

        # Phantom-duplicate loophole close: no token routed us to the no-tenant DB
        # and no server-scoped row exists for this fqdn — but if it already lives
        # in a TENANT DB, creating one here would duplicate it across partitions.
        # (Only reached on the token-less path; a token already picked the tenant.)
        if enrollment_tenant_id is None:
            _reject_if_fqdn_belongs_to_tenant(registration_data.fqdn)

        # Race guard: if this fqdn+ipv4 was just cascade-deleted by a
        # child-host delete, the doomed VM's agent is racing virsh
        # destroy with a final /host/register.  Absorb it without
        # recreating a ghost Host row — the agent is about to die so
        # the response doesn't matter.  See
        # backend.api.recent_host_deletions for the full rationale.
        from backend.api.recent_host_deletions import is_recent_child_host_deletion

        if is_recent_child_host_deletion(
            registration_data.fqdn, registration_data.ipv4
        ):
            logger.info(
                "Absorbed last-gasp registration for recently-deleted "
                "child host fqdn=%s ipv4=%s",
                sanitize_log(registration_data.fqdn),
                sanitize_log(registration_data.ipv4),
            )
            return {
                "result": True,
                "message": _("Registration absorbed: host was recently deleted"),
                "absorbed": True,
            }

        # Phase 13.1.F: enforce the enrolling tenant's host quota BEFORE creating
        # the row (no-op single-tenant / when no limit is set).  Only new hosts
        # reach here, so a tenant at its cap can still refresh its current fleet.
        host_utils.enforce_tenant_host_quota(
            session, enrollment_tenant_id, registration_data.fqdn
        )

        # Phase 8.1: validate optional registration_key BEFORE creating
        # the host row, so a bad key never even creates a pending host.
        validated_key = _validate_registration_key(
            session, registration_data.registration_key
        )

        # Create new host with pending approval status and minimal data
        host = models.Host(
            fqdn=registration_data.fqdn,
            active=registration_data.active,
            ipv4=registration_data.ipv4,
            ipv6=registration_data.ipv6,
            last_access=datetime.now(timezone.utc),
        )

        # Auto-approve when the matched key allows it; otherwise pending.
        if validated_key is not None and validated_key.auto_approve:
            host.approval_status = "approved"
        else:
            host.approval_status = "pending"

        # NOTE: Script execution capability defaults to False for new hosts
        # This should only be enabled through explicit admin configuration after registration
        host.script_execution_enabled = False
        session.add(host)
        session.flush()  # need host.id for join-table inserts below

        # Phase 8.1: enroll into the key's access group + bump usage.  Atomic
        # with the host create — one commit below.
        _apply_registration_key_enrollment(session, host, validated_key)

        session.commit()
        session.refresh(host)

        # Phase 13.1: record the host→tenant binding so the data plane routes
        # this host's data to its tenant's database.  The token was already
        # validated + consumed above; this writes the index + audits it.
        if enrollment_tenant_id is not None:
            from backend.services import host_tenant_index  # noqa: PLC0415

            host_tenant_index.bind_host_to_tenant(host.id, enrollment_tenant_id)
            AuditService.log(
                db=session,
                action_type=ActionType.CREATE,
                entity_type=EntityType.HOST,
                entity_id=str(host.id),
                entity_name=host.fqdn,
                description=_(
                    "Host '%(fqdn)s' enrolled into tenant %(tenant_id)s via enrollment token"
                )
                % {"fqdn": host.fqdn, "tenant_id": enrollment_tenant_id},
                result=Result.SUCCESS,
                details={"tenant_id": enrollment_tenant_id},
            )

        # Audit log: enrollment via registration key carries enough
        # context that the operator can correlate to the matched key.
        if validated_key is not None:
            AuditService.log(
                db=session,
                action_type=ActionType.CREATE,
                entity_type=EntityType.HOST,
                entity_id=str(host.id),
                entity_name=host.fqdn,
                description=_(
                    "Host '%(fqdn)s' enrolled via registration key '%(key_name)s' (auto_approve=%(auto_approve)s)"
                )
                % {
                    "fqdn": host.fqdn,
                    "key_name": validated_key.name,
                    "auto_approve": validated_key.auto_approve,
                },
                result=Result.SUCCESS,
                details={
                    "registration_key_id": str(validated_key.id),
                    "registration_key_name": validated_key.name,
                    "access_group_id": (
                        str(validated_key.access_group_id)
                        if validated_key.access_group_id
                        else None
                    ),
                    "auto_approved": validated_key.auto_approve,
                },
            )

        # Phase 10.4.4 — auto-apply default mirror assignments for the
        # newly-enrolled host's (platform, version, os_family).  Only
        # for approved hosts; pending hosts get applied when an admin
        # approves them (separate hook in approve_host).  Best-effort:
        # any failure is logged and swallowed so registration itself
        # never breaks because of a mirror engine quirk.
        if host.approval_status == "approved":
            try:
                from backend.api.repository_mirroring import (
                    apply_default_mirrors_for_new_host,
                )

                apply_default_mirrors_for_new_host(str(host.id))
            except (
                Exception
            ) as exc:  # pylint: disable=broad-except  # nosec B110 - mirror auto-apply is best-effort
                logger.warning(
                    "Default-mirror auto-apply failed for host %s: %s",
                    host.fqdn,
                    exc,
                )

        return host


@auth_router.put("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def update_host(
    host_id: str, host_data: Host, current_user: str = Depends(get_current_user)
):
    """
    This function updates an existing host by id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Update the user
    with session_local() as session:
        # Get the user object for audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=error_user_not_found())
        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail=error_host_not_found())

        # Update the values
        session.query(models.Host).filter(models.Host.id == host_id).update(
            {
                models.Host.active: host_data.active,
                models.Host.fqdn: host_data.fqdn,
                models.Host.ipv4: host_data.ipv4,
                models.Host.ipv6: host_data.ipv6,
                models.Host.last_access: datetime.now(timezone.utc),
            }
        )
        session.commit()

        # Get updated host data after commit
        updated_host = (
            session.query(models.Host).filter(models.Host.id == host_id).first()
        )

        # Audit log host update
        AuditService.log_update(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host_data.fqdn,
            details={
                "active": host_data.active,
                "ipv4": host_data.ipv4,
                "ipv6": host_data.ipv6,
            },
        )

        # Return dictionary to avoid detached object issues
        return {
            "id": str(updated_host.id),
            "active": updated_host.active,
            "fqdn": updated_host.fqdn,
            "ipv4": updated_host.ipv4,
            "ipv6": updated_host.ipv6,
            "last_access": (
                updated_host.last_access.replace(tzinfo=timezone.utc).isoformat()
                if updated_host.last_access
                else None
            ),
            "status": updated_host.status,
            "approval_status": updated_host.approval_status,
        }


# Include the extracted routers
auth_router.include_router(host_approval.router, tags=["hosts"])
auth_router.include_router(host_data_updates.router, tags=["hosts"])
auth_router.include_router(host_graylog.router, tags=["hosts"])
auth_router.include_router(host_monitoring.router, tags=["hosts"])
auth_router.include_router(host_operations.router, tags=["hosts"])
auth_router.include_router(host_ubuntu_pro.router, tags=["hosts"])
auth_router.include_router(host_account_management.router, tags=["hosts"])
