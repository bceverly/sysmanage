# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Package data handlers for SysManage agent communication.
Handles available packages messages from agents.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, delete, or_
from sqlalchemy.orm import Session

from backend.api.error_constants import error_host_not_registered
from backend.api.package_host_selector import host_matches_os
from backend.i18n import _
from backend.persistence.models import AvailablePackage, Host

# Logger for debugging - use existing root logger configuration
debug_logger = logging.getLogger("debug_logger")


# OLD NON-PAGINATED HANDLER REMOVED - USE PAGINATED HANDLERS ONLY


# Global storage for batched package data (in-memory for now)
_batch_sessions = {}


async def handle_packages_batch_start(db: Session, connection, message_data: dict):
    """Handle the start of a paginated available packages batch."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    try:
        # Get host information for OS details
        host = db.query(Host).filter(Host.id == connection.host_id).first()
        if not host:
            return {
                "message_type": "error",
                "error_type": "host_not_found",
                "message": _("Host not found"),
                "data": {},
            }

        # Get batch information
        batch_id = message_data.get("batch_id")
        if not batch_id:
            return {
                "message_type": "error",
                "error_type": "missing_batch_id",
                "message": _("Missing batch_id"),
                "data": {},
            }

        os_name = message_data.get("os_name") or host.platform or "Unknown"
        os_version = (
            message_data.get("os_version") or host.platform_release or "Unknown"
        )
        package_managers = message_data.get("package_managers", [])

        # Validate that the host is reporting packages for its own OS.
        #
        # This used to compare the agent's DISTRIBUTION ("Ubuntu", "26.04")
        # directly against the host's PLATFORM ("Linux") and platform_release
        # ("Ubuntu 26.04") -- fields that were never going to match on any Linux
        # distro.  Every Linux batch was therefore rejected, the catalog never
        # landed, and because the automatic trigger fires when a
        # (os_name, os_version) has NO rows, the server re-requested the whole
        # ~89k catalog on the next OS update, for ever.  Measured 2026-08-06:
        # 78,979 messages / 9.4 GB in eight days, 83% of all agent traffic.
        # FreeBSD masked it -- there distribution == platform == "FreeBSD".
        #
        # host_matches_os owns the convention (see package_host_selector).
        if not host_matches_os(host, os_name, os_version):
            error_msg = _(
                "Host %(host_fqdn)s (%(host_platform)s %(host_platform_release)s) "
                "attempted to report packages for %(os_name)s %(os_version)s"
            ) % {
                "host_fqdn": host.fqdn,
                "host_platform": host.platform,
                "host_platform_release": host.platform_release,
                "os_name": os_name,
                "os_version": os_version,
            }
            debug_logger.error(error_msg)
            return {
                "message_type": "error",
                "error_type": "os_mismatch",
                "message": error_msg,
                "data": {},
            }

        debug_logger.info(
            "Starting available packages batch %s for host %s (%s %s) with managers: %s",
            batch_id,
            connection.host_id,
            os_name,
            os_version,
            package_managers,
        )

        # Clear THIS HOST's existing packages for the managers it is about to
        # report.  Scoped by host_id on purpose: deleting by (os_name,
        # os_version) wiped the rows of every other host running the same OS,
        # so two hosts reporting concurrently clobbered each other and a host
        # that failed part-way through left the catalog truncated for all of
        # them.  Legacy rows (host_id IS NULL) predate scoping and are cleared
        # for this OS as well, so the first scoped report replaces them rather
        # than double-counting alongside them.
        for manager_name in package_managers:
            db.execute(
                delete(AvailablePackage).where(
                    AvailablePackage.package_manager == manager_name,
                    or_(
                        AvailablePackage.host_id == str(connection.host_id),
                        and_(
                            AvailablePackage.host_id.is_(None),
                            AvailablePackage.os_name == os_name,
                            AvailablePackage.os_version == os_version,
                        ),
                    ),
                )
            )
        db.commit()

        # Initialize batch session.  The catalog fingerprint travels with the
        # batch and is persisted only when the batch COMPLETES (see
        # handle_packages_batch_end): recording it here would claim we hold a
        # catalog that is still in flight, and a batch that then failed would
        # leave the agent skipping future sends of data we never stored.
        _batch_sessions[batch_id] = {
            "host_id": connection.host_id,
            "os_name": os_name,
            "os_version": os_version,
            "package_managers": package_managers,
            "total_packages": 0,
            "catalog_fingerprint": message_data.get("catalog_fingerprint"),
            "started_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }

        return {
            "message_type": "acknowledgment",
            "status": "batch_started",
            "batch_id": batch_id,
        }

    except Exception as e:
        db.rollback()
        debug_logger.exception(
            "Error starting available packages batch for host %s: %s",
            connection.host_id,
            e,
        )
        return {
            "message_type": "error",
            "error_type": "batch_start_failed",
            "message": _("Failed to start packages batch: %s") % str(e),
            "data": {},
        }


async def handle_packages_batch(db: Session, connection, message_data: dict):  # NOSONAR
    """Handle a batch of available packages data."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    try:
        batch_id = message_data.get("batch_id")
        if not batch_id or batch_id not in _batch_sessions:
            return {
                "message_type": "error",
                "error_type": "invalid_batch_id",
                "message": _("Invalid or expired batch_id"),
                "data": {},
            }

        batch_session = _batch_sessions[batch_id]

        # Verify this is the same host
        if batch_session["host_id"] != connection.host_id:
            return {
                "message_type": "error",
                "error_type": "batch_host_mismatch",
                "message": _("Batch belongs to different host"),
                "data": {},
            }

        # Process packages from this batch
        package_managers = message_data.get("package_managers", {})
        batch_packages = 0

        for manager_name, packages in package_managers.items():
            if not packages:
                continue

            debug_logger.info(
                "Processing batch with %d packages from %s for host %s (batch %s)",
                len(packages),
                manager_name,
                connection.host_id,
                batch_id,
            )

            # Insert packages from this batch
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for package in packages:
                package_name = package.get("name", "").strip()
                package_version = package.get("version", "").strip()
                package_description = package.get("description", "").strip()

                if not package_name or not package_version:
                    debug_logger.warning(
                        "Skipping invalid package: name='%s', version='%s'",
                        package_name,
                        package_version,
                    )
                    continue

                # Truncate description if too long for database
                if len(package_description) > 1000:
                    package_description = package_description[:997] + "..."

                available_package = AvailablePackage(
                    host_id=str(batch_session["host_id"]),
                    package_name=package_name,
                    package_version=package_version,
                    package_description=package_description,
                    package_manager=manager_name,
                    os_name=batch_session["os_name"],
                    os_version=batch_session["os_version"],
                    created_at=now,
                    last_updated=now,
                )
                db.add(available_package)
                batch_packages += 1

        # Commit this batch
        db.commit()
        batch_session["total_packages"] += batch_packages

        debug_logger.info(
            "Processed batch %s: %d packages (total so far: %d)",
            batch_id,
            batch_packages,
            batch_session["total_packages"],
        )

        return {
            "message_type": "acknowledgment",
            "status": "batch_processed",
            "batch_id": batch_id,
            "packages_in_batch": batch_packages,
        }

    except Exception as e:
        db.rollback()
        debug_logger.exception(
            "Error processing available packages batch for host %s: %s",
            connection.host_id,
            e,
        )
        return {
            "message_type": "error",
            "error_type": "batch_process_failed",
            "message": _("Failed to process packages batch: %s") % str(e),
            "data": {},
        }


async def handle_packages_batch_end(db: Session, connection, message_data: dict):
    """Handle the end of a paginated available packages batch."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    try:
        batch_id = message_data.get("batch_id")
        if not batch_id or batch_id not in _batch_sessions:
            return {
                "message_type": "error",
                "error_type": "invalid_batch_id",
                "message": _("Invalid or expired batch_id"),
                "data": {},
            }

        batch_session = _batch_sessions[batch_id]

        # Verify this is the same host
        if batch_session["host_id"] != connection.host_id:
            return {
                "message_type": "error",
                "error_type": "batch_host_mismatch",
                "message": _("Batch belongs to different host"),
                "data": {},
            }

        total_packages = batch_session["total_packages"]

        debug_logger.info(
            "Completed available packages batch %s for host %s (%s %s): %d total packages",
            batch_id,
            connection.host_id,
            batch_session["os_name"],
            batch_session["os_version"],
            total_packages,
        )

        # Record what we now hold, so the next collect command can hand this
        # fingerprint back and the agent can skip re-sending an identical
        # catalog.  Written ONLY here, on successful completion -- a batch that
        # failed part-way must not leave us claiming a catalog we do not have,
        # or the agent would skip sends for data that was never stored.
        fingerprint = batch_session.get("catalog_fingerprint")
        if fingerprint:
            host = db.query(Host).filter(Host.id == connection.host_id).first()
            if host:
                host.available_packages_fingerprint = fingerprint
                host.available_packages_fingerprint_at = datetime.now(
                    timezone.utc
                ).replace(tzinfo=None)
                db.commit()

        # Clean up batch session
        del _batch_sessions[batch_id]

        return {
            "message_type": "acknowledgment",
            "status": "batch_completed",
            "batch_id": batch_id,
            "total_packages_processed": total_packages,
        }

    except Exception as e:
        debug_logger.exception(
            "Error ending available packages batch for host %s: %s",
            connection.host_id,
            e,
        )
        return {
            "message_type": "error",
            "error_type": "batch_end_failed",
            "message": _("Failed to end packages batch: %s") % str(e),
            "data": {},
        }


def _apply_takes(db: Session, host_id: str, takes: list) -> None:
    """Remove packages the machine no longer offers, scoped to THIS host.

    A malformed entry is skipped rather than fatal: one bad row must not abort
    a delta that is otherwise applicable.
    """
    for take in takes:
        manager = (take.get("package_manager") or "").strip()
        name = (take.get("name") or "").strip()
        if not manager or not name:
            continue
        db.execute(
            delete(AvailablePackage).where(
                AvailablePackage.host_id == host_id,
                AvailablePackage.package_manager == manager,
                AvailablePackage.package_name == name,
            )
        )


def _upsert_package(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session, host_id: str, fields: dict, os_pair: tuple, now
) -> None:
    """Write one package row, replacing the existing one if there is one.

    A version change REPLACES rather than accumulating a second row -- duplicates
    would inflate every OS-level count and make the stored catalog disagree with
    the fingerprint both sides think they share.
    """
    existing = (
        db.query(AvailablePackage)
        .filter(
            AvailablePackage.host_id == host_id,
            AvailablePackage.package_manager == fields["manager"],
            AvailablePackage.package_name == fields["name"],
        )
        .first()
    )
    if existing:
        existing.package_version = fields["version"]
        existing.package_description = fields["description"]
        existing.last_updated = now
        return

    db.add(
        AvailablePackage(
            host_id=host_id,
            package_name=fields["name"],
            package_version=fields["version"],
            package_description=fields["description"],
            package_manager=fields["manager"],
            os_name=os_pair[0],
            os_version=os_pair[1],
            created_at=now,
            last_updated=now,
        )
    )


def _put_fields(put: dict) -> Optional[dict]:
    """Normalise one put, or None when it is unusable.

    Skipping a malformed entry is deliberate: one bad row must not abort a delta
    that is otherwise applicable.
    """
    manager = (put.get("package_manager") or "").strip()
    name = (put.get("name") or "").strip()
    version = (put.get("version") or "").strip()
    if not manager or not name or not version:
        return None
    description = (put.get("description") or "").strip()
    if len(description) > 1000:
        description = description[:997] + "..."
    return {
        "manager": manager,
        "name": name,
        "version": version,
        "description": description,
    }


def _apply_puts(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session, host_id: str, puts: list, message_data: dict, host, now
) -> int:
    """Upsert every added/changed package the machine reported."""
    # Resolved ONCE: these do not vary per package, and recomputing an or-chain
    # for each of ~89k rows is pure waste.
    os_pair = (
        message_data.get("os_name") or host.platform or "Unknown",
        message_data.get("os_version") or host.platform_release or "Unknown",
    )
    applied = 0
    for put in puts:
        fields = _put_fields(put)
        if fields is None:
            continue
        _upsert_package(db, host_id, fields, os_pair, now)
        applied += 1
    return applied


async def handle_packages_delta(db: Session, connection, message_data: dict):
    """Apply an incremental catalog update: puts (added/changed) + takes (removed).

    WHY A DELTA NEEDS A BASE
    -----------------------
    A diff only means anything relative to the catalog it was computed against.
    The agent sends the fingerprint of that base; if it is not the catalog we
    actually hold, the diff describes changes to something else and applying it
    would leave our copy quietly wrong -- and wrong FOR EVER, because every
    later delta is applied on top of the damage.

    So a mismatched base is rejected outright.  The agent's response to a
    rejection is to send a full catalog, which is always correct, so refusing
    here costs one large message and never costs correctness.

    Puts are upserts keyed by (host, manager, name): a version change replaces
    the row rather than accumulating a second one.  Takes delete by the same
    key.  Everything is scoped to THIS host -- the catalog is per-host, and a
    delta from one host must never touch another's rows.
    """
    from backend.utils.host_validation import validate_host_id

    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    try:
        host = db.query(Host).filter(Host.id == connection.host_id).first()
        if not host:
            return {
                "message_type": "error",
                "error_type": "host_not_found",
                "message": _("Host not found"),
                "data": {},
            }

        base = message_data.get("base_fingerprint")
        held = host.available_packages_fingerprint
        if not base or base != held:
            # Not an error in the agent -- just a base we cannot honour.  Logged
            # at warning because a PERSISTENT mismatch means the two sides never
            # re-synchronise, which is worth noticing.
            debug_logger.warning(
                "Rejecting package delta from host %s: base fingerprint %s does "
                "not match the catalog we hold (%s); agent will send a full catalog",
                host.fqdn,
                base,
                held,
            )
            return {
                "message_type": "error",
                "error_type": "delta_base_mismatch",
                "message": _("Delta base does not match the stored catalog"),
                "data": {"held_fingerprint": held},
            }

        puts = message_data.get("puts") or []
        takes = message_data.get("takes") or []
        host_id = str(connection.host_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        _apply_takes(db, host_id, takes)
        applied_puts = _apply_puts(db, host_id, puts, message_data, host, now)

        # The catalog we now hold is the one the agent says results from this
        # delta.  Recorded only after the changes are applied, for the same
        # reason batch_end records it only on completion: claiming a catalog we
        # do not have makes the agent skip sending it, silently and for ever.
        new_fingerprint = message_data.get("new_fingerprint")
        if new_fingerprint:
            host.available_packages_fingerprint = new_fingerprint
            host.available_packages_fingerprint_at = now
        db.commit()

        debug_logger.info(
            "Applied package delta for host %s: %d put(s), %d take(s), catalog now %s",
            host.fqdn,
            applied_puts,
            len(takes),
            (new_fingerprint or "unchanged")[:12],
        )

        return {
            "message_type": "acknowledgment",
            "status": "delta_applied",
            "puts_applied": applied_puts,
            "takes_applied": len(takes),
        }

    except Exception as e:
        db.rollback()
        debug_logger.exception(
            "Error applying package delta for host %s: %s", connection.host_id, e
        )
        return {
            "message_type": "error",
            "error_type": "delta_failed",
            "message": _("Failed to apply package delta: %s") % str(e),
            "data": {},
        }
