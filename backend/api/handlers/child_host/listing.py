"""
Child host listing handlers.

This module handles child host listing messages from agents,
including discovery and synchronization of child hosts.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host, HostChild
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


def _try_link_child_to_approved_host(
    db: Session, child: HostChild, now: datetime
) -> Optional[Host]:
    """
    Try to link a running child host to an already-approved Host record.

    This handles the race condition where a host is approved before the parent
    agent reports it as a child host. When the parent later reports the child,
    we check if there's an approved host with matching hostname and link them.

    Args:
        db: Database session
        child: The HostChild record to potentially link
        now: Current timestamp for setting installed_at

    Returns:
        The matched Host if linked, None otherwise
    """
    if not child.hostname:
        return None

    # Already linked
    if child.child_host_id is not None:
        return None

    # Only link running children
    if child.status != "running":
        return None

    # Try exact FQDN match first (case-insensitive)
    matching_host = (
        db.query(Host)
        .filter(
            func.lower(Host.fqdn) == func.lower(child.hostname),
            Host.approval_status == "approved",
        )
        .first()
    )

    # If no exact match, try matching by short hostname
    if not matching_host:
        child_short_name = (
            child.hostname.split(".")[0] if "." in child.hostname else None
        )
        if child_short_name:
            # Find hosts where fqdn starts with the short name followed by a dot
            matching_host = (
                db.query(Host)
                .filter(
                    func.lower(Host.fqdn).like(func.lower(child_short_name + ".%")),
                    Host.approval_status == "approved",
                )
                .first()
            )

    # If still no match, check if child.hostname is a short name that matches
    # a host's fqdn prefix
    if not matching_host and "." not in child.hostname:
        matching_host = (
            db.query(Host)
            .filter(
                func.lower(Host.fqdn).like(func.lower(child.hostname + ".%")),
                Host.approval_status == "approved",
            )
            .first()
        )

    if matching_host:
        # Link the child to the approved host
        child.child_host_id = matching_host.id
        child.installed_at = now
        # Also set parent_host_id on the host record for easier filtering
        matching_host.parent_host_id = child.parent_host_id
        logger.info(
            "Linked child host %s (%s) to approved host %s (%s) - late linking",
            child.child_name,
            child.id,
            matching_host.id,
            matching_host.fqdn,
        )
        return matching_host

    return None


async def handle_child_hosts_list_update(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle child hosts list result from agent.

    Updates the host_child table with discovered child hosts.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing child hosts list

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning("Child hosts list update received but no host_id on connection")
        return {
            "message_type": "error",
            "error_type": "no_host_id",
            "message": _("No host_id on connection"),
            "data": {},
        }

    result_data = message_data.get("result", {})
    if not result_data:
        result_data = message_data

    # Check for success - it may be at top level (command_result) or in result_data
    success = message_data.get("success", result_data.get("success", False))
    if not success:
        error = message_data.get("error") or result_data.get("error", "Unknown error")
        logger.error("Child hosts list failed for host %s: %s", host_id, error)
        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": error,
            "data": {},
        }

    child_hosts = result_data.get("child_hosts", [])
    count = result_data.get("count", len(child_hosts))

    logger.info("Child hosts list for host %s: %d child hosts found", host_id, count)

    try:
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning("Host not found for child hosts update: %s", host_id)
            return {
                "message_type": "error",
                "error_type": "host_not_found",
                "message": _("Host not found"),
                "data": {},
            }

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Get existing child hosts for this parent
        existing_children = (
            db.query(HostChild).filter(HostChild.parent_host_id == host_id).all()
        )
        existing_by_key = {(c.child_name, c.child_type): c for c in existing_children}

        # Track which children we've seen
        seen_keys = set()
        new_count = 0
        updated_count = 0
        linked_count = 0

        for child_data in child_hosts:
            child_name = child_data.get("child_name")
            child_type = child_data.get("child_type")
            status = child_data.get("status", "unknown")

            if not child_name or not child_type:
                logger.warning("Child host missing name or type: %s", child_data)
                continue

            key = (child_name, child_type)
            seen_keys.add(key)

            # Get distribution info
            distribution_info = child_data.get("distribution", {})
            distribution_name = None
            distribution_version = None
            if isinstance(distribution_info, dict):
                distribution_name = distribution_info.get("distribution_name")
                distribution_version = distribution_info.get("distribution_version")

            # Get hostname (only available for running instances)
            hostname = child_data.get("hostname")

            # Get WSL GUID (used to prevent stale delete commands)
            wsl_guid = child_data.get("wsl_guid")

            if key in existing_by_key:
                # Update existing child host
                child = existing_by_key[key]
                # Don't overwrite "uninstalling" status - it should only clear
                # when the delete completes and agent stops reporting the child
                # Also don't update updated_at for uninstalling children so they
                # can properly become stale and get cleaned up
                if child.status != "uninstalling":
                    child.status = status
                    child.updated_at = now
                if distribution_name:
                    child.distribution = distribution_name
                if distribution_version:
                    child.distribution_version = distribution_version
                # Always update hostname from agent (may have changed)
                if hostname:
                    child.hostname = hostname
                # Always update wsl_guid from agent
                if wsl_guid:
                    child.wsl_guid = wsl_guid
                updated_count += 1

                # Try to link unlinked running children to approved hosts
                # This handles race condition where host was approved before
                # the parent reported this child
                if _try_link_child_to_approved_host(db, child, now):
                    linked_count += 1
            else:
                # Create new child host record
                child = HostChild(
                    parent_host_id=host_id,
                    child_name=child_name,
                    child_type=child_type,
                    status=status,
                    distribution=distribution_name,
                    distribution_version=distribution_version,
                    hostname=hostname,
                    wsl_guid=wsl_guid,
                    created_at=now,
                    updated_at=now,
                )
                db.add(child)
                new_count += 1

                # Flush to get the child ID, then try to link
                db.flush()
                if _try_link_child_to_approved_host(db, child, now):
                    linked_count += 1

        # Remove children that were not reported by the agent
        # If the agent doesn't see them, they've been deleted outside of sysmanage
        # BUT preserve records in "creating" status - they're still being set up
        # AND preserve "uninstalling" records briefly to allow the delete handler to
        # process the confirmation and clean up host records properly
        missing_count = 0
        stale_threshold = now - timedelta(minutes=10)  # 10 minutes is long enough

        for key, child in existing_by_key.items():
            if key not in seen_keys:
                # Don't delete if still in "creating" status - the instance
                # doesn't exist yet so the agent won't report it
                if child.status == "creating":
                    logger.debug(
                        "Preserving child host %s (%s) - still in creating status",
                        child.child_name,
                        child.child_type,
                    )
                    continue

                # For "uninstalling" status, preserve briefly to allow delete handler
                # to process, but clean up if stale (delete command failed/timed out)
                if child.status == "uninstalling":
                    if child.updated_at and child.updated_at > stale_threshold:
                        logger.debug(
                            "Preserving child host %s (%s) - uninstalling in progress",
                            child.child_name,
                            child.child_type,
                        )
                        continue

                    # Stale uninstalling record - the delete command likely failed
                    # Also delete any corresponding host record
                    if child.child_host_id:
                        linked_host = (
                            db.query(Host)
                            .filter(Host.id == child.child_host_id)
                            .first()
                        )
                        if linked_host:
                            logger.info(
                                "Deleting linked host record for stale uninstalling "
                                "child %s: host_id=%s",
                                child.child_name,
                                child.child_host_id,
                            )
                            db.delete(linked_host)
                    elif child.hostname:
                        # Try to find host by fqdn (Host model uses fqdn, not hostname)
                        # Extract short hostname (first part before any dot)
                        child_short_hostname = child.hostname.split(".")[0]

                        matching_host = (
                            db.query(Host)
                            .filter(func.lower(Host.fqdn) == func.lower(child.hostname))
                            .first()
                        )
                        # Try prefix match (hostname without domain)
                        if not matching_host:
                            matching_host = (
                                db.query(Host)
                                .filter(
                                    func.lower(Host.fqdn).like(
                                        func.lower(child.hostname + ".%")
                                    )
                                )
                                .first()
                            )
                        # Try reverse prefix match (Host.fqdn is short, hostname is FQDN)
                        if not matching_host:
                            matching_host = (
                                db.query(Host)
                                .filter(
                                    func.lower(child.hostname).like(
                                        func.lower(Host.fqdn) + ".%"
                                    )
                                )
                                .first()
                            )
                        # Try matching just the short hostname
                        if not matching_host:
                            matching_host = (
                                db.query(Host)
                                .filter(
                                    func.lower(Host.fqdn)
                                    == func.lower(child_short_hostname)
                                )
                                .first()
                            )
                        # Try matching short hostname as prefix of Host.fqdn
                        if not matching_host:
                            matching_host = (
                                db.query(Host)
                                .filter(
                                    func.lower(Host.fqdn).like(
                                        func.lower(child_short_hostname + ".%")
                                    )
                                )
                                .first()
                            )
                        if matching_host:
                            logger.info(
                                "Deleting matching host record for stale uninstalling "
                                "child %s: fqdn=%s",
                                child.child_name,
                                matching_host.fqdn,
                            )
                            db.delete(matching_host)

                    logger.info(
                        "Deleting stale uninstalling child host %s (%s) - "
                        "not reported by agent for >10 minutes",
                        child.child_name,
                        child.child_type,
                    )

                # Child was not reported - it has been removed
                db.delete(child)
                missing_count += 1
                logger.info(
                    "Deleted child host %s (%s) - no longer reported by agent",
                    child.child_name,
                    child.child_type,
                )

        db.commit()

        logger.info(
            "Child hosts update for host %s: new=%d, updated=%d, linked=%d, missing=%d",
            host_id,
            new_count,
            updated_count,
            linked_count,
            missing_count,
        )

        AuditService.log(
            db=db,
            action_type=ActionType.AGENT_MESSAGE,
            entity_type=EntityType.HOST,
            entity_id=str(host_id),
            entity_name=host.fqdn,
            description=_("Child hosts list updated"),
            result=Result.SUCCESS,
            details={
                "total_reported": count,
                "new_count": new_count,
                "updated_count": updated_count,
                "linked_count": linked_count,
                "missing_count": missing_count,
            },
        )

        return {
            "message_type": "child_hosts_list_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "updated",
            "new_count": new_count,
            "updated_count": updated_count,
            "linked_count": linked_count,
        }

    except Exception as e:
        db.rollback()
        logger.error(
            "Error updating child hosts list for host %s: %s", host_id, e, exc_info=True
        )
        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": str(e),
            "data": {},
        }
