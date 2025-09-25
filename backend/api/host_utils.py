"""
Utility functions for host management operations.
Contains common database operations and helper functions for host API endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.i18n import _
from backend.persistence import db, models


def get_host_by_id(host_id: str) -> Optional[models.Host]:
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


def get_host_storage_devices(host_id: str) -> List[Dict[str, Any]]:
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

        def determine_device_type(device_name: str, stored_type: str) -> str:
            """Determine if device is physical or logical based on its name and type."""
            # If the stored_type is already "physical" or "logical", use it directly
            # (this handles cases where the agent correctly determines the type)
            if stored_type in ["physical", "logical"]:
                return stored_type

            device_lower = device_name.lower() if device_name else ""

            # Windows physical drive patterns
            if "physicaldrive" in device_lower:
                return "physical"

            # Windows logical drive patterns (drive letters)
            if device_name and len(device_name) == 2 and device_name[1] == ":":
                return "logical"

            # Logical volume patterns (check first as they're more specific)
            logical_patterns = [
                "tmpfs",
                "mfs",
                "procfs",
                "kernfs",
                "devfs",
                "zroot/",
                "tank/",
                "rpool/",  # ZFS datasets
            ]

            # Check for logical volumes first
            for pattern in logical_patterns:
                if pattern in device_lower:
                    return "logical"

            # Physical device patterns for FreeBSD/BSD systems
            # These patterns match device names like ada0, cd0, nvd0, etc.
            physical_device_types = ["ada", "da", "cd", "nvd", "wd", "sd"]

            # Check if it's a physical device
            for dev_type in physical_device_types:
                # Check /dev/ prefixed names
                if device_lower.startswith(f"/dev/{dev_type}"):
                    return "physical"
                # Check bare device names like "ada0", "cd0"
                if device_lower.startswith(dev_type):
                    # Make sure it's followed by a number
                    remainder = device_lower[len(dev_type) :]
                    if remainder and remainder[0].isdigit():
                        return "physical"

            # Network mounts are logical
            if ":/" in device_name:  # NFS-style mounts
                return "logical"

            # Default for /dev/ devices is physical, everything else logical
            return "physical" if device_name.startswith("/dev/") else "logical"

        result = []
        for device in storage_devices:
            device_type = determine_device_type(device.device_name, device.device_type)
            result.append(
                {
                    "id": str(device.id),
                    "name": device.device_name,
                    "mount_point": device.mount_point,
                    "file_system": device.filesystem,
                    "device_type": device_type,
                    "is_physical": bool(device_type == "physical"),  # Ensure boolean
                    "capacity_bytes": device.total_size_bytes,
                    "used_bytes": device.used_size_bytes,
                    "available_bytes": device.available_size_bytes,
                    "last_updated": (
                        device.last_updated.isoformat() if device.last_updated else None
                    ),
                    # Legacy fields for backward compatibility
                    "size_gb": (
                        round(device.total_size_bytes / (1024**3), 2)
                        if device.total_size_bytes
                        else 0
                    ),
                    "used_gb": (
                        round(device.used_size_bytes / (1024**3), 2)
                        if device.used_size_bytes
                        else 0
                    ),
                    "available_gb": (
                        round(device.available_size_bytes / (1024**3), 2)
                        if device.available_size_bytes
                        else 0
                    ),
                    "usage_percent": (
                        round(
                            (device.used_size_bytes / device.total_size_bytes) * 100, 1
                        )
                        if device.total_size_bytes and device.used_size_bytes
                        else 0
                    ),
                }
            )
        return result


def get_host_network_interfaces(host_id: str) -> List[Dict[str, Any]]:
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
                "id": str(interface.id),
                "name": interface.interface_name,
                "interface_type": interface.interface_type,
                "mac_address": interface.mac_address,
                "ipv4_address": interface.ipv4_address,
                "ipv6_address": interface.ipv6_address,
                "netmask": interface.netmask,
                "broadcast": interface.broadcast,
                "mtu": interface.mtu,
                "is_up": interface.is_up,
                "speed_mbps": interface.speed_mbps,
                "last_updated": (
                    interface.last_updated.isoformat()
                    if interface.last_updated
                    else None
                ),
            }
            for interface in interfaces
        ]


def get_host_user_accounts(host_id: str) -> List[Dict[str, Any]]:
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
                "id": str(user.id),
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


def get_host_users_with_groups(host_id: str) -> List[Dict[str, Any]]:
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

            # For Windows hosts, check if shell field contains Windows SID
            uid_value = user.uid
            shell_value = user.shell
            if (
                hasattr(host, "platform")
                and host.platform
                and "windows" in host.platform.lower()
            ):
                # Windows SIDs are stored in shell field if uid is None
                if user.uid is None and user.shell and user.shell.startswith("S-1-"):
                    uid_value = user.shell  # Return Windows SID as uid for frontend
                    shell_value = None  # Don't show shell for Windows

            users.append(
                {
                    "id": str(user.id),
                    "username": user.username,
                    "uid": uid_value,
                    "home_directory": user.home_directory,
                    "shell": shell_value,
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


def get_host_user_groups(host_id: str) -> List[Dict[str, Any]]:
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
                    "id": str(group.id),
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


def get_host_software_packages(host_id: str) -> List[Dict[str, Any]]:
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
                "id": str(package.id),
                "package_name": package.package_name,
                "version": package.package_version,
                "description": package.package_description,
                "package_manager": package.package_manager,
                "architecture": package.architecture,
                "size_bytes": package.size_bytes,
                "vendor": package.vendor,
                "category": package.category,
                "license": package.license,
                "install_path": package.install_path,
                "install_date": (
                    package.install_date.isoformat() if package.install_date else None
                ),
                "is_system_package": package.is_system_package,
                "created_at": (
                    package.created_at.isoformat() if package.created_at else None
                ),
                "updated_at": (
                    package.updated_at.isoformat() if package.updated_at else None
                ),
            }
            for package in packages
        ]


def update_host_timestamp(host_id: str, field_name: str) -> None:
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
    db_session,
    hostname: str,
    ipv4: str = None,
    ipv6: str = None,
    script_execution_enabled: bool = False,
):
    """
    Update existing host record or create a new one.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info("=== HOST UTILS DEBUG ===")
    logger.info("Hostname: %s", hostname)
    logger.info("Script execution enabled parameter: %s", script_execution_enabled)

    host = db_session.query(models.Host).filter(models.Host.fqdn == hostname).first()
    logger.info("Found existing host: %s", host is not None)

    if host:
        # Update existing host
        logger.info(
            "Updating existing host with script_execution_enabled=%s",
            script_execution_enabled,
        )
        host.ipv4 = ipv4
        host.ipv6 = ipv6
        host.last_access = datetime.now(timezone.utc)
        host.active = True
        host.status = "up"
        # Update script execution status from agent
        host.script_execution_enabled = script_execution_enabled
        # If agent can enable script execution, it's running in privileged mode
        host.is_agent_privileged = script_execution_enabled
        logger.info(
            "Set is_agent_privileged=%s, script_execution_enabled=%s",
            script_execution_enabled,
            script_execution_enabled,
        )

        # Generate host_token for existing hosts that don't have one (migration support)
        if not host.host_token:
            from backend.persistence.models import generate_secure_host_token

            host.host_token = generate_secure_host_token()
            logger.info("Generated new host_token for existing host")

        # Don't modify approval_status for existing hosts - preserve the current status
    else:
        # Create new host with pending approval status
        logger.info(
            "Creating new host with script_execution_enabled=%s",
            script_execution_enabled,
        )
        # Generate secure host token
        from backend.persistence.models import generate_secure_host_token

        host_token = generate_secure_host_token()

        host = models.Host(
            fqdn=hostname,
            ipv4=ipv4,
            ipv6=ipv6,
            host_token=host_token,  # Assign secure token
            last_access=datetime.now(timezone.utc),
            active=True,
            status="up",
            approval_status="pending",  # New hosts need approval
            script_execution_enabled=script_execution_enabled,  # Set from agent message
            is_agent_privileged=script_execution_enabled,  # If agent can enable scripts, it's privileged
        )
        db_session.add(host)

    db_session.commit()
    db_session.refresh(host)
    return host


def get_host_ubuntu_pro_info(host_id: str) -> Dict[str, Any]:
    """Get Ubuntu Pro information for a specific host."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # First check if the host exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get Ubuntu Pro info with services
        ubuntu_pro_info = (
            session.query(models.UbuntuProInfo)
            .filter(models.UbuntuProInfo.host_id == host_id)
            .first()
        )

        if not ubuntu_pro_info:
            # Return empty structure if no Ubuntu Pro data
            return {
                "available": False,
                "attached": False,
                "version": None,
                "expires": None,
                "account_name": None,
                "contract_name": None,
                "tech_support_level": None,
                "services": [],
            }

        # Get services
        services = (
            session.query(models.UbuntuProService)
            .filter(models.UbuntuProService.ubuntu_pro_info_id == ubuntu_pro_info.id)
            .all()
        )

        # Format service data
        services_data = [
            {
                "name": service.service_name,
                "description": "",  # Not stored in database
                "available": service.status != "n/a",  # Available if status is not n/a
                "status": service.status,
                "entitled": service.entitled == "true",
            }
            for service in services
        ]

        return {
            "available": True,  # If we have Ubuntu Pro data, it's available
            "attached": ubuntu_pro_info.attached,
            "version": ubuntu_pro_info.subscription_name,
            "expires": (
                ubuntu_pro_info.expires.isoformat() if ubuntu_pro_info.expires else None
            ),
            "account_name": ubuntu_pro_info.account_name,
            "contract_name": ubuntu_pro_info.contract_name,
            "tech_support_level": ubuntu_pro_info.tech_support_level,
            "services": services_data,
        }
