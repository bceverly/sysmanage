"""
Utility functions for host management operations.
Contains common database operations and helper functions for host API endpoints.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.persistence import db, models
from backend.i18n import _


def get_host_by_id(host_id: int) -> Optional[models.Host]:
    """Get a host by ID, raising HTTPException if not found."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))
        return host


def get_host_by_fqdn(fqdn: str) -> Optional[models.Host]:
    """Get a host by FQDN, raising HTTPException if not found."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        host = session.query(models.Host).filter(models.Host.fqdn == fqdn).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))
        return host


def validate_host_approval_status(host: models.Host) -> None:
    """Validate that a host is approved for operations."""
    if host.approval_status != "approved":
        raise HTTPException(status_code=400, detail=_("Host is not approved"))


def get_host_storage_devices(host_id: int) -> List[Dict[str, Any]]:
    """Get storage devices for a host."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Verify host exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get storage devices
        storage_devices = (
            session.query(models.StorageDevice)
            .filter(models.StorageDevice.host_id == host_id)
            .all()
        )

        return [
            {
                "id": device.id,
                "name": device.name,
                "device_path": device.device_path,
                "mount_point": device.mount_point,
                "file_system": device.file_system,
                "size_gb": (
                    round(device.capacity_bytes / (1024**3), 2)
                    if device.capacity_bytes
                    else 0
                ),
                "used_gb": (
                    round(device.used_bytes / (1024**3), 2) if device.used_bytes else 0
                ),
                "available_gb": (
                    round(device.available_bytes / (1024**3), 2)
                    if device.available_bytes
                    else 0
                ),
                "usage_percent": (
                    round((device.used_bytes / device.capacity_bytes) * 100, 1)
                    if device.capacity_bytes and device.used_bytes
                    else 0
                ),
                "device_type": device.device_type,
            }
            for device in storage_devices
        ]


def get_host_network_interfaces(host_id: int) -> List[Dict[str, Any]]:
    """Get network interfaces for a host."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Verify host exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get network interfaces
        interfaces = (
            session.query(models.NetworkInterface)
            .filter(models.NetworkInterface.host_id == host_id)
            .all()
        )

        return [
            {
                "id": interface.id,
                "name": interface.name,
                "interface_type": interface.interface_type,
                "hardware_type": interface.hardware_type,
                "mac_address": interface.mac_address,
                "ipv4_address": interface.ipv4_address,
                "ipv6_address": interface.ipv6_address,
                "subnet_mask": interface.subnet_mask,
                "is_active": interface.is_active,
                "speed_mbps": interface.speed_mbps,
                "created_at": (
                    interface.created_at.isoformat() if interface.created_at else None
                ),
                "updated_at": (
                    interface.updated_at.isoformat() if interface.updated_at else None
                ),
            }
            for interface in interfaces
        ]


def get_host_user_accounts(host_id: int) -> List[Dict[str, Any]]:
    """Get user accounts for a host."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Verify host exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get user accounts
        users = (
            session.query(models.UserAccount)
            .filter(models.UserAccount.host_id == host_id)
            .all()
        )

        return [
            {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "home_directory": user.home_directory,
                "shell": user.shell,
                "user_id": user.user_id,
                "group_id": user.group_id,
                "is_system_user": user.is_system_user,
                "is_active": user.is_active,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            }
            for user in users
        ]


def get_host_users_with_groups(host_id: int) -> List[Dict[str, Any]]:
    """Get user accounts with group memberships for a host."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Verify host exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get user accounts
        user_accounts = (
            session.query(models.UserAccount)
            .filter(models.UserAccount.host_id == host_id)
            .all()
        )

        # Convert to JSON-compatible format with group memberships
        users = []
        for user in user_accounts:
            # Get group memberships for this user
            group_memberships = (
                session.query(models.UserGroupMembership, models.UserGroup)
                .join(
                    models.UserGroup,
                    models.UserGroupMembership.user_group_id == models.UserGroup.id,
                )
                .filter(models.UserGroupMembership.user_account_id == user.id)
                .all()
            )

            group_names = [group.group_name for _, group in group_memberships]

            users.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "uid": user.uid,
                    "home_directory": user.home_directory,
                    "shell": user.shell,
                    "is_system_user": user.is_system_user,
                    "groups": group_names,
                    "created_at": (
                        user.created_at.isoformat() if user.created_at else None
                    ),
                    "updated_at": (
                        user.updated_at.isoformat() if user.updated_at else None
                    ),
                }
            )

        return users


def get_host_user_groups(host_id: int) -> List[Dict[str, Any]]:
    """Get user groups for a host."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Verify host exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get user groups
        user_groups = (
            session.query(models.UserGroup)
            .filter(models.UserGroup.host_id == host_id)
            .all()
        )

        groups = []
        for group in user_groups:
            # Get user memberships for this group
            user_memberships = (
                session.query(models.UserGroupMembership, models.UserAccount)
                .join(
                    models.UserAccount,
                    models.UserGroupMembership.user_account_id == models.UserAccount.id,
                )
                .filter(models.UserGroupMembership.user_group_id == group.id)
                .all()
            )

            user_names = [user.username for _, user in user_memberships]
            groups.append(
                {
                    "id": group.id,
                    "group_name": group.group_name,
                    "gid": group.gid,
                    "is_system_group": group.is_system_group,
                    "users": user_names,
                    "created_at": (
                        group.created_at.isoformat() if group.created_at else None
                    ),
                    "updated_at": (
                        group.updated_at.isoformat() if group.updated_at else None
                    ),
                }
            )

        return groups


def get_host_software_packages(host_id: int) -> List[Dict[str, Any]]:
    """Get software packages for a host."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Verify host exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get software packages
        packages = (
            session.query(models.SoftwarePackage)
            .filter(models.SoftwarePackage.host_id == host_id)
            .order_by(models.SoftwarePackage.package_name)
            .all()
        )

        return [
            {
                "id": package.id,
                "package_name": package.package_name,
                "version": package.version,
                "description": package.description,
                "package_manager": package.package_manager,
                "source": package.source,
                "architecture": package.architecture,
                "size_bytes": package.size_bytes,
                "install_date": (
                    package.install_date.isoformat() if package.install_date else None
                ),
                "vendor": package.vendor,
                "category": package.category,
                "license_type": package.license_type,
                "bundle_id": package.bundle_id,
                "app_store_id": package.app_store_id,
                "installation_path": package.installation_path,
                "is_system_package": package.is_system_package,
                "is_user_installed": package.is_user_installed,
                "created_at": (
                    package.created_at.isoformat() if package.created_at else None
                ),
                "updated_at": (
                    package.updated_at.isoformat() if package.updated_at else None
                ),
                "software_updated_at": (
                    package.software_updated_at.isoformat()
                    if package.software_updated_at
                    else None
                ),
            }
            for package in packages
        ]


def update_host_timestamp(host_id: int, field_name: str) -> None:
    """Update a timestamp field for a host."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if host:
            setattr(host, field_name, datetime.now(timezone.utc))
            session.commit()


async def update_or_create_host(
    db_session, hostname: str, ipv4: str = None, ipv6: str = None
):
    """
    Update existing host record or create a new one.
    """
    host = db_session.query(models.Host).filter(models.Host.fqdn == hostname).first()

    if host:
        # Update existing host
        host.ipv4 = ipv4
        host.ipv6 = ipv6
        host.last_access = datetime.now(timezone.utc)
        host.active = True
        host.status = "up"
        # Don't modify approval_status for existing hosts - preserve the current status
    else:
        # Create new host with pending approval status
        host = models.Host(
            fqdn=hostname,
            ipv4=ipv4,
            ipv6=ipv6,
            last_access=datetime.now(timezone.utc),
            active=True,
            status="up",
            approval_status="pending",  # New hosts need approval
        )
        db_session.add(host)

    db_session.commit()
    db_session.refresh(host)
    return host
