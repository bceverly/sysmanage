"""
Software and Package data handlers for SysManage agent communication.
Handles software inventory, package updates, available packages, third-party repositories, and antivirus status.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import (
    AntivirusStatus,
    AvailablePackage,
    CommercialAntivirusStatus,
    FirewallStatus,
    GraylogAttachment,
    Host,
    PackageUpdate,
    SoftwarePackage,
    ThirdPartyRepository,
)

# Logger for debugging - use existing root logger configuration
debug_logger = logging.getLogger("debug_logger")


async def handle_software_update(db: Session, connection, message_data: dict):
    """Handle software inventory update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Handle software packages
        software_packages = message_data.get("software_packages", [])
        if software_packages:
            # Delete existing software packages for this host
            db.execute(
                delete(SoftwarePackage).where(
                    SoftwarePackage.host_id == connection.host_id
                )
            )

            # Add new software packages
            for package in software_packages:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                software_package = SoftwarePackage(
                    host_id=connection.host_id,
                    package_name=package.get("package_name"),
                    package_version=package.get("version") or "unknown",
                    package_manager=package.get("package_manager", "unknown"),
                    package_description=package.get("description"),
                    architecture=package.get("architecture"),
                    install_path=package.get("installation_path"),
                    created_at=now,
                    updated_at=now,
                )
                db.add(software_package)

        # Update the software updated timestamp on the host
        stmt = (
            update(Host)
            .where(Host.id == connection.host_id)
            .values(software_updated_at=datetime.now(timezone.utc))
        )
        db.execute(stmt)

        db.commit()

        debug_logger.info(
            "Software inventory updated for host %s: %d packages",
            connection.host_id,
            len(software_packages),
        )

        return {
            "message_type": "success",
            "result": _("software_inventory_updated"),
        }

    except Exception as e:
        debug_logger.error("Error updating software inventory: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update software inventory"),
        }


async def handle_package_updates_update(db: Session, connection, message_data: dict):
    """Handle package updates information from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Clear existing updates for this host first
        db.execute(
            delete(PackageUpdate).where(PackageUpdate.host_id == connection.host_id)
        )

        # Process available updates
        available_updates = message_data.get("available_updates", [])
        total_updates = len(available_updates)

        debug_logger.info(
            "Processing %d package updates for host %s",
            total_updates,
            connection.host_id,
        )

        # Debug: log first package update structure to understand data format
        if available_updates:
            debug_logger.info(
                "Sample package update structure: %s", available_updates[0]
            )

        for package_update in available_updates:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            # Debug: log all keys in this package update
            debug_logger.info(
                "Package update keys for %s: %s",
                package_update.get("package_name", "unknown"),
                list(package_update.keys()),
            )

            # Handle case where new_version is None - skip if no version available
            new_version = package_update.get("new_version") or package_update.get(
                "available_version"
            )
            debug_logger.info(
                "Package %s: new_version=%s, available_version=%s, resolved=%s",
                package_update.get("package_name", "unknown"),
                package_update.get("new_version"),
                package_update.get("available_version"),
                new_version,
            )

            if not new_version:
                debug_logger.warning(
                    "Skipping package update %s - no new version available",
                    package_update.get("package_name", "unknown"),
                )
                continue

            # Map agent data to database model fields
            is_security = package_update.get("is_security_update", False)
            is_system = package_update.get("is_system_update", False)

            # Determine update type based on agent flags
            if is_security:
                update_type = "security"
            elif is_system:
                update_type = "system"
            else:
                update_type = "enhancement"

            # Get bundle_id or update_id (Windows Update uses update_id)
            bundle_id = package_update.get("bundle_id") or package_update.get(
                "update_id"
            )

            package_update_record = PackageUpdate(
                host_id=connection.host_id,
                package_name=package_update.get("package_name"),
                bundle_id=bundle_id,  # Actual package ID for package managers (bundle_id for winget, update_id for Windows Update)
                current_version=package_update.get("current_version") or "unknown",
                available_version=new_version,  # Use validated version
                package_manager=package_update.get("package_manager", "unknown"),
                update_type=update_type,
                size_bytes=package_update.get("update_size"),
                requires_reboot=False,  # Default, could be enhanced later
                # Required timestamp fields
                discovered_at=now,
                created_at=now,
                updated_at=now,
            )
            try:
                db.add(package_update_record)
                debug_logger.info(
                    "Added package update: %s %s -> %s (%s)",
                    package_update.get("package_name"),
                    package_update.get("current_version"),
                    new_version,
                    update_type,
                )
            except Exception as e:
                debug_logger.error(
                    "Failed to add package update %s: %s",
                    package_update.get("package_name", "unknown"),
                    str(e),
                )

        # Only update host's last access timestamp if this is from a live connection
        # (not from background queue processing of old messages)
        if (
            not hasattr(connection, "is_mock_connection")
            or not connection.is_mock_connection
        ):
            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(last_access=datetime.now(timezone.utc).replace(tzinfo=None))
            )
            db.execute(stmt)

        db.commit()

        debug_logger.info(
            "Package updates stored successfully for host %s: %d updates",
            connection.host_id,
            total_updates,
        )

        return {
            "message_type": "success",
            "updates_processed": total_updates,
        }

    except Exception as e:
        debug_logger.error("Error storing package updates: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to store updates: %s") % str(e),
        }


async def handle_package_collection(db: Session, connection, message_data: dict):
    """Handle package collection result from agent."""
    debug_logger.info(
        "Processing package collection result from %s",
        getattr(connection, "hostname", "unknown"),
    )

    try:
        # Extract package data from the message
        packages = message_data.get("packages", {})
        os_name = message_data.get("os_name", "Unknown")
        os_version = message_data.get("os_version", "Unknown")
        hostname = message_data.get("hostname")
        total_packages = message_data.get("total_packages", 0)

        debug_logger.info(
            "Package collection data: OS=%s %s, hostname=%s, total_packages=%d, package_managers=%s",
            os_name,
            os_version,
            hostname,
            total_packages,
            list(packages.keys()) if packages else "none",
        )

        if not packages:
            debug_logger.warning("No package data received in command result")
            return {
                "message_type": "package_collection_result_ack",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "no_data",
            }

        # Clear existing packages for this OS/version combination
        debug_logger.info("Clearing existing packages for %s %s", os_name, os_version)
        delete_stmt = delete(AvailablePackage).where(
            AvailablePackage.os_name == os_name,
            AvailablePackage.os_version == os_version,
        )
        db.execute(delete_stmt)

        # Process each package manager's packages
        total_inserted = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for package_manager, package_list in packages.items():
            debug_logger.info(
                "Processing %d packages from %s", len(package_list), package_manager
            )

            batch_packages = []
            for package in package_list:
                available_package = AvailablePackage(
                    os_name=os_name,
                    os_version=os_version,
                    package_manager=package_manager,
                    package_name=package.get("name", ""),
                    package_version=package.get("version", ""),
                    package_description=package.get("description", ""),
                    last_updated=now,
                    created_at=now,
                )
                batch_packages.append(available_package)

                # Insert in batches to avoid memory issues
                if len(batch_packages) >= 1000:
                    db.add_all(batch_packages)
                    db.flush()
                    total_inserted += len(batch_packages)
                    batch_packages = []

            # Insert remaining packages
            if batch_packages:
                db.add_all(batch_packages)
                db.flush()
                total_inserted += len(batch_packages)

            debug_logger.info(
                "Completed processing %s packages, total inserted so far: %d",
                package_manager,
                total_inserted,
            )

        # Commit all changes
        db.commit()

        debug_logger.info(
            "Successfully stored %d packages for %s %s",
            total_inserted,
            os_name,
            os_version,
        )

        return {
            "message_type": "package_collection_result_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
            "packages_stored": total_inserted,
        }

    except Exception as e:
        debug_logger.error(
            "Error processing package collection result from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()

        return {
            "message_type": "error",
            "error": f"Failed to process package collection result: {str(e)}",
        }


async def handle_third_party_repository_update(
    db: Session, connection, message_data: dict
):
    """Handle third-party repository update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Handle third-party repositories
        repositories = message_data.get("repositories", [])

        debug_logger.info(
            "Processing third-party repository update from %s with %d repositories",
            getattr(connection, "hostname", "unknown"),
            len(repositories),
        )

        # Delete existing repositories for this host
        db.execute(
            delete(ThirdPartyRepository).where(
                ThirdPartyRepository.host_id == connection.host_id
            )
        )

        # Add new repositories
        repos_added = 0
        for repo in repositories:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            repository = ThirdPartyRepository(
                host_id=connection.host_id,
                name=repo.get("name", ""),
                type=repo.get("type", "unknown"),
                url=repo.get("url"),
                enabled=repo.get("enabled", True),
                file_path=repo.get("file_path"),
                last_updated=now,
            )
            db.add(repository)
            repos_added += 1

        # Update host timestamp
        host = db.query(Host).filter(Host.id == connection.host_id).first()
        if host:
            # We don't have a specific timestamp field for third-party repos yet,
            # but we can use last_access or add one in the future
            pass

        db.commit()

        debug_logger.info(
            "Successfully stored %d third-party repositories for host %s",
            repos_added,
            getattr(connection, "hostname", "unknown"),
        )

        return {
            "message_type": "third_party_repository_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
            "repositories_stored": repos_added,
        }

    except Exception as e:
        debug_logger.error(
            "Error processing third-party repository update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process third-party repository update: {str(e)}",
        }


async def handle_antivirus_status_update(db: Session, connection, message_data: dict):
    """Handle antivirus status update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Extract antivirus status information
        software_name = message_data.get("software_name")
        install_path = message_data.get("install_path")
        version = message_data.get("version")
        enabled = message_data.get("enabled")

        debug_logger.info(
            "Processing antivirus status update from %s: software=%s, enabled=%s",
            getattr(connection, "hostname", "unknown"),
            software_name,
            enabled,
        )

        # Delete existing antivirus status for this host (if any)
        db.execute(
            delete(AntivirusStatus).where(AntivirusStatus.host_id == connection.host_id)
        )

        # Add new antivirus status (only if software is detected)
        if software_name:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            antivirus_status = AntivirusStatus(
                host_id=connection.host_id,
                software_name=software_name,
                install_path=install_path,
                version=version,
                enabled=enabled,
                last_updated=now,
            )
            db.add(antivirus_status)

        db.commit()

        debug_logger.info(
            "Successfully stored antivirus status for host %s",
            getattr(connection, "hostname", "unknown"),
        )

        return {
            "message_type": "antivirus_status_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
        }

    except Exception as e:
        debug_logger.error(
            "Error processing antivirus status update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process antivirus status update: {str(e)}",
        }


async def handle_commercial_antivirus_status_update(
    db: Session, connection, message_data: dict
):
    """Handle commercial antivirus status update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Extract commercial antivirus status information
        product_name = message_data.get("product_name")
        product_version = message_data.get("product_version")
        service_enabled = message_data.get("service_enabled")
        antispyware_enabled = message_data.get("antispyware_enabled")
        antivirus_enabled = message_data.get("antivirus_enabled")
        realtime_protection_enabled = message_data.get("realtime_protection_enabled")
        full_scan_age = message_data.get("full_scan_age")
        quick_scan_age = message_data.get("quick_scan_age")
        full_scan_end_time = message_data.get("full_scan_end_time")
        quick_scan_end_time = message_data.get("quick_scan_end_time")
        signature_last_updated = message_data.get("signature_last_updated")
        signature_version = message_data.get("signature_version")
        tamper_protection_enabled = message_data.get("tamper_protection_enabled")

        debug_logger.info(
            "Processing commercial antivirus status update from %s: product=%s, enabled=%s",
            getattr(connection, "hostname", "unknown"),
            product_name,
            antivirus_enabled,
        )

        # Parse datetime strings if provided
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if full_scan_end_time:
            try:
                full_scan_end_time = datetime.fromisoformat(full_scan_end_time).replace(
                    tzinfo=None
                )
            except (ValueError, AttributeError):
                full_scan_end_time = None

        if quick_scan_end_time:
            try:
                quick_scan_end_time = datetime.fromisoformat(
                    quick_scan_end_time
                ).replace(tzinfo=None)
            except (ValueError, AttributeError):
                quick_scan_end_time = None

        if signature_last_updated:
            try:
                signature_last_updated = datetime.fromisoformat(
                    signature_last_updated
                ).replace(tzinfo=None)
            except (ValueError, AttributeError):
                signature_last_updated = None

        # Delete existing commercial antivirus status for this host (if any)
        db.execute(
            delete(CommercialAntivirusStatus).where(
                CommercialAntivirusStatus.host_id == connection.host_id
            )
        )

        # Add new commercial antivirus status (only if product is detected)
        if product_name:
            commercial_antivirus_status = CommercialAntivirusStatus(
                host_id=connection.host_id,
                product_name=product_name,
                product_version=product_version,
                service_enabled=service_enabled,
                antispyware_enabled=antispyware_enabled,
                antivirus_enabled=antivirus_enabled,
                realtime_protection_enabled=realtime_protection_enabled,
                full_scan_age=full_scan_age,
                quick_scan_age=quick_scan_age,
                full_scan_end_time=full_scan_end_time,
                quick_scan_end_time=quick_scan_end_time,
                signature_last_updated=signature_last_updated,
                signature_version=signature_version,
                tamper_protection_enabled=tamper_protection_enabled,
                created_at=now,
                last_updated=now,
            )
            db.add(commercial_antivirus_status)

        db.commit()

        debug_logger.info(
            "Successfully stored commercial antivirus status for host %s",
            getattr(connection, "hostname", "unknown"),
        )

        return {
            "message_type": "commercial_antivirus_status_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
        }

    except Exception as e:
        debug_logger.error(
            "Error processing commercial antivirus status update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process commercial antivirus status update: {str(e)}",
        }


async def handle_firewall_status_update(db: Session, connection, message_data: dict):
    """Handle firewall status update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Extract firewall status information
        firewall_name = message_data.get("firewall_name")
        enabled = message_data.get("enabled", False)
        tcp_open_ports = message_data.get(
            "tcp_open_ports"
        )  # JSON string or list (legacy)
        udp_open_ports = message_data.get(
            "udp_open_ports"
        )  # JSON string or list (legacy)
        ipv4_ports = message_data.get("ipv4_ports")  # JSON string or list
        ipv6_ports = message_data.get("ipv6_ports")  # JSON string or list

        debug_logger.info(
            "Processing firewall status update from %s: firewall=%s, enabled=%s",
            getattr(connection, "hostname", "unknown"),
            firewall_name,
            enabled,
        )

        # Delete existing firewall status for this host (if any)
        db.execute(
            delete(FirewallStatus).where(FirewallStatus.host_id == connection.host_id)
        )

        # Add new firewall status
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Convert lists to JSON strings if needed
        import json

        if isinstance(tcp_open_ports, list):
            tcp_open_ports = json.dumps(tcp_open_ports)
        if isinstance(udp_open_ports, list):
            udp_open_ports = json.dumps(udp_open_ports)
        if isinstance(ipv4_ports, list):
            ipv4_ports = json.dumps(ipv4_ports)
        if isinstance(ipv6_ports, list):
            ipv6_ports = json.dumps(ipv6_ports)

        firewall_status = FirewallStatus(
            host_id=connection.host_id,
            firewall_name=firewall_name,
            enabled=enabled,
            tcp_open_ports=tcp_open_ports,
            udp_open_ports=udp_open_ports,
            ipv4_ports=ipv4_ports,
            ipv6_ports=ipv6_ports,
            last_updated=now,
        )
        db.add(firewall_status)
        db.commit()

        debug_logger.info(
            "Successfully stored firewall status for host %s",
            getattr(connection, "hostname", "unknown"),
        )

        return {
            "message_type": "firewall_status_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
        }

    except Exception as e:
        debug_logger.error(
            "Error processing firewall status update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process firewall status update: {str(e)}",
        }


async def handle_graylog_status_update(db: Session, connection, message_data: dict):
    """Handle Graylog attachment status update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Extract Graylog status information
        is_attached = message_data.get("is_attached", False)
        target_hostname = message_data.get("target_hostname")
        target_ip = message_data.get("target_ip")
        mechanism = message_data.get("mechanism")
        port = message_data.get("port")

        debug_logger.info(
            "Processing Graylog status update from %s: is_attached=%s, mechanism=%s",
            getattr(connection, "hostname", "unknown"),
            is_attached,
            mechanism,
        )

        # Delete existing Graylog status for this host (if any)
        db.execute(
            delete(GraylogAttachment).where(
                GraylogAttachment.host_id == connection.host_id
            )
        )

        # Add new Graylog status
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        graylog_attachment = GraylogAttachment(
            host_id=connection.host_id,
            is_attached=is_attached,
            target_hostname=target_hostname,
            target_ip=target_ip,
            mechanism=mechanism,
            port=port,
            detected_at=now,
            updated_at=now,
        )
        db.add(graylog_attachment)
        db.commit()

        debug_logger.info(
            "Successfully stored Graylog attachment status for host %s",
            getattr(connection, "hostname", "unknown"),
        )

        return {
            "message_type": "graylog_status_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
        }

    except Exception as e:
        debug_logger.error(
            "Error processing Graylog status update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process Graylog status update: {str(e)}",
        }
