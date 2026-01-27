"""
Data processing utilities for WebSocket agent communication.
Contains functions for processing various types of system data from agents.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.persistence.models import (
    SoftwarePackage,
    UserAccount,
    UserGroup,
    UserGroupMembership,
)

debug_logger = logging.getLogger("websocket_debug")


def process_user_accounts(db: Session, host_id: str, users_data: list):
    """Process user accounts data for a host."""
    for user_data in users_data:
        if not user_data.get("error"):  # Skip error entries
            user_account = UserAccount(
                host_id=host_id,
                username=user_data.get("username"),
                uid=user_data.get("uid"),
                home_directory=user_data.get("home_directory"),
                shell=user_data.get("shell"),  # nosec B604
                is_system_user=user_data.get("is_system_user", False),
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(user_account)


def process_user_groups(db: Session, host_id: str, groups_data: list):
    """Process user groups data for a host."""
    for group_data in groups_data:
        if not group_data.get("error"):  # Skip error entries
            user_group = UserGroup(
                host_id=host_id,
                group_name=group_data.get("group_name"),
                gid=group_data.get("gid"),
                is_system_group=group_data.get("is_system_group", False),
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(user_group)


def process_user_group_memberships(  # NOSONAR
    db: Session, host_id: str, users_data: list, user_id_map: dict, group_id_map: dict
):
    """Process user-group memberships for a host."""
    debug_logger.info("Processing memberships for %d users", len(users_data))
    debug_logger.info(
        "Available users: %d, Available groups: %d", len(user_id_map), len(group_id_map)
    )

    membership_count = 0
    for user_data in users_data:
        if not user_data.get("error") and "groups" in user_data:
            username = user_data.get("username")
            groups_list = user_data.get("groups", [])

            if username in user_id_map:
                user_account_id = user_id_map[username]
                for group_name in groups_list:
                    if group_name in group_id_map:
                        group_id = group_id_map[group_name]
                        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
                        membership = UserGroupMembership(
                            host_id=host_id,
                            user_account_id=user_account_id,
                            user_group_id=group_id,
                            created_at=current_time,
                            updated_at=current_time,
                        )
                        db.merge(membership)
                        membership_count += 1
                    else:
                        debug_logger.debug(
                            "Group '%s' not found in group_id_map for user %s",
                            group_name,
                            username,
                        )
            else:
                debug_logger.debug("User '%s' not found in user_id_map", username)
        else:
            if user_data.get("error"):
                debug_logger.debug(
                    "Skipping user with error: %s", user_data.get("username", "unknown")
                )
            elif "groups" not in user_data:
                debug_logger.debug(
                    "User %s has no groups field", user_data.get("username", "unknown")
                )

    debug_logger.info("Added %d memberships to database", membership_count)


def process_software_packages(db: Session, host_id: str, packages_data: list):
    """Process software packages data for a host."""
    package_count = 0
    for package_data in packages_data:
        if not package_data.get("error"):  # Skip error entries
            software_package = SoftwarePackage(
                host_id=host_id,
                package_name=package_data.get("package_name"),
                package_version=package_data.get("version") or "unknown",
                package_description=package_data.get("description"),
                package_manager=package_data.get("package_manager") or "unknown",
                architecture=package_data.get("architecture"),
                size_bytes=package_data.get("size_bytes"),
                install_date=package_data.get("install_date"),
                vendor=package_data.get("vendor"),
                category=package_data.get("category"),
                license=package_data.get("license_type"),
                install_path=package_data.get("installation_path"),
                is_system_package=package_data.get("is_system_package", False),
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(software_package)
            package_count += 1
        else:
            debug_logger.debug(
                "Skipping package with error: %s",
                package_data.get("package_name", "unknown"),
            )

    debug_logger.info("Added %d software packages to database", package_count)
