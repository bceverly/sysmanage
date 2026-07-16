# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
GPG key command-result handlers (GPG Key Management — Slice 3b).

Consumes the agent's ``install_gpg_key`` / ``remove_gpg_key``
``command_result`` messages and flips the ``status`` on the matching
``gpg_key_assignment`` row.  This is a purely mechanical status update on an
OSS table — the command DISPATCH and key material handling live in the
licensed ``secrets_engine`` (Pro+); nothing here touches key material.

``db`` is the caller's session, already tenant-routed to the bound host's
database (the caller owns the session lifecycle).  Following the sibling
convention (e.g. ``handle_user_access_update``), this handler resolves the
host from ``connection.host_id`` and commits its own transaction.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.persistence.models.gpg_key import (
    ASSIGNMENT_FAILED,
    ASSIGNMENT_INSTALLED,
    ASSIGNMENT_PENDING,
    GpgKeyAssignment,
)

logger = logging.getLogger(__name__)


def _extract_fields(message_data: Dict[str, Any]):
    """Pull ``command_type``, ``success`` and the nested result fields out of a
    command_result message.  Mirrors the extraction idiom used elsewhere in
    ``handle_command_result`` (top-level or nested ``command_type``; a
    ``result`` dict carrying the payload).  NEVER logs / returns key material."""
    command_type = message_data.get("command_type") or message_data.get("data", {}).get(
        "command_type"
    )

    result_data = message_data.get("result")
    if not isinstance(result_data, dict):
        result_data = message_data.get("data")
    if not isinstance(result_data, dict):
        result_data = {}

    # ``success`` may live at the top level or inside the result payload.
    success = message_data.get("success")
    if success is None:
        success = result_data.get("success")

    # ``key_id`` identifies the GpgKey (== GpgKeyAssignment.gpg_key_id).
    key_id = result_data.get("key_id")
    if key_id is None:
        key_id = message_data.get("key_id")

    # NULL target_username == host-level assignment.
    target_username = result_data.get("target_username")
    if target_username is None and "target_username" in message_data:
        target_username = message_data.get("target_username")

    return command_type, bool(success), key_id, target_username


def _find_assignment(db: Session, host_id, key_id, target_username, prefer_pending):
    """Return the matching ``GpgKeyAssignment`` for this host/key/user, or None.

    When ``prefer_pending`` is set, a ``pending`` row is preferred (the install
    flow), so a fresh assignment is flipped rather than an older terminal row.
    """
    query = db.query(GpgKeyAssignment).filter(
        GpgKeyAssignment.host_id == host_id,
        GpgKeyAssignment.gpg_key_id == key_id,
        GpgKeyAssignment.target_username == target_username,
    )
    if prefer_pending:
        pending = query.filter(GpgKeyAssignment.status == ASSIGNMENT_PENDING).first()
        if pending is not None:
            return pending
    return query.first()


async def handle_gpg_key_command_result(  # NOSONAR
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Flip ``gpg_key_assignment.status`` from an install/remove command result.

    Host is resolved from ``connection.host_id`` (sibling convention).  For an
    install the row's status becomes ``installed`` (or ``failed``).  For a
    remove a successful result deletes the row outright, while a failure sets
    ``failed`` so the (still-visible) assignment can be retried.  Missing host,
    missing fields, or an absent assignment are handled gracefully — we never
    raise."""
    command_type, success, key_id, target_username = _extract_fields(message_data)

    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "GPG %s result but connection has no host_id; ignoring", command_type
        )
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": "Host not registered",
            "data": {},
        }

    if not key_id:
        logger.warning(
            "GPG %s result for host %s missing key_id; ignoring",
            command_type,
            host_id,
        )
        return {"message_type": "command_result_ack"}

    try:
        if command_type == "install_gpg_key":
            assignment = _find_assignment(
                db, host_id, key_id, target_username, prefer_pending=True
            )
            if assignment is None:
                logger.warning(
                    "GPG install result for host %s key %s user %s: no matching "
                    "assignment found; ignoring",
                    host_id,
                    key_id,
                    target_username,
                )
                return {"message_type": "command_result_ack"}

            assignment.status = ASSIGNMENT_INSTALLED if success else ASSIGNMENT_FAILED
            db.commit()
            logger.info(
                "GPG install result for host %s key %s user %s -> status=%s",
                host_id,
                key_id,
                target_username,
                assignment.status,
            )
            return {"message_type": "command_result_ack"}

        if command_type == "remove_gpg_key":
            assignment = _find_assignment(
                db, host_id, key_id, target_username, prefer_pending=False
            )
            if assignment is None:
                # The DELETE-assignment endpoint now keeps the row in the
                # ``removing`` state until the agent confirms, so a missing row
                # here means it was already reaped (e.g. a duplicate result).
                # No-op gracefully.
                logger.info(
                    "GPG remove result for host %s key %s user %s: no assignment "
                    "row to reconcile; no-op",
                    host_id,
                    key_id,
                    target_username,
                )
                return {"message_type": "command_result_ack"}

            if success:
                # Truly removed on the agent — drop the row for good.
                db.delete(assignment)
                db.commit()
                logger.info(
                    "GPG remove result for host %s key %s user %s -> row deleted",
                    host_id,
                    key_id,
                    target_username,
                )
            else:
                # Removal failed — keep the row visible/retryable.
                assignment.status = ASSIGNMENT_FAILED
                db.commit()
                logger.info(
                    "GPG remove result for host %s key %s user %s -> status=%s",
                    host_id,
                    key_id,
                    target_username,
                    assignment.status,
                )
            return {"message_type": "command_result_ack"}

        logger.warning(
            "handle_gpg_key_command_result called with unexpected command_type %s",
            command_type,
        )
        return {"message_type": "command_result_ack"}

    except Exception as exc:  # pylint: disable=broad-exception-caught
        db.rollback()
        logger.exception(
            "Error processing GPG %s result for host %s key %s: %s",
            command_type,
            host_id,
            key_id,
            exc,
        )
        return {
            "message_type": "error",
            "error_type": "gpg_key_result_error",
            "message": "Failed to process GPG key command result",
            "data": {},
        }
