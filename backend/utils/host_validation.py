# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Host validation utilities for SysManage server.
Contains shared validation functions to avoid circular imports.
"""

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host


def _host_exists_in_other_partition(host_id: str, hostname: str = None) -> bool:
    """Return True if the host lives in ANY tenant database (multi-tenancy only).

    ``validate_host_id`` is handed whatever session the caller happens to hold —
    frequently the bootstrap session (e.g. a heartbeat whose connection hasn't
    resolved its tenant engine yet, or an index that briefly lagged).  Under
    multi-tenancy the host's row actually lives in its TENANT database, so a
    bootstrap-only lookup misses a perfectly valid host.

    Reporting that as ``host_not_registered`` is the ROOT of the phantom-duplicate
    churn: the agent reacts by discarding its identity and re-registering, burning
    enrollment-token uses until a token-less registration spawns a server-scoped
    ghost row.  So before we ever tell an agent it isn't registered, resolve the
    host across the host→tenant index / tenant databases here — the authoritative
    "does this host exist anywhere?" answer.

    Cheap no-op when multi-tenancy is disabled (no tenant DBs to scan).  Only an
    existence check: the tenant session opened by the resolver is closed
    immediately (data-plane routing writes the host's data to the right DB
    elsewhere; here we only answer "is it registered?").
    """
    from backend.config import config as _config  # noqa: PLC0415

    if not _config.is_multitenancy_enabled():
        return False

    try:
        from backend.websocket.inbound_processor import (  # noqa: PLC0415
            _find_host_in_tenant_dbs,
        )

        found, session = _find_host_in_tenant_dbs(host_id, hostname)
    except (
        Exception
    ):  # noqa: BLE001 — never let a resolver hiccup emit a false negative
        return False

    if session is not None:
        session.close()
    return found is not None


async def validate_host_id(
    db: Session, connection, host_id: str, hostname: str = None
) -> bool:
    """
    Validate that a host_id exists in the database.
    Returns True if host exists, False if not.
    Sends error message to agent if host doesn't exist.

    If hostname is provided, also validate by hostname as fallback.

    Multi-tenancy: a host's row lives in its tenant database while the caller may
    only hold the bootstrap session, so a miss here is NOT proof the host is gone.
    Before sending ``host_not_registered`` (which makes the agent destroy its
    identity and re-register — the phantom-duplicate churn) we resolve the host
    across every tenant database.  The error is sent ONLY when the host exists in
    no partition at all.
    """
    if not host_id:
        return True  # No host_id to validate

    # First try to find by exact host_id
    host = db.query(Host).filter(Host.id == host_id).first()

    # If not found by ID but we have hostname, try finding by hostname
    # This handles cases where agent sends incorrect host_id but correct hostname
    if not host and hostname:
        host = db.query(Host).filter(Host.fqdn == hostname).first()
        if host:
            # Found by hostname - this is valid, agent just has wrong ID
            return True

    # Not in the session we were handed — check the tenant databases before
    # declaring the host unregistered (see _host_exists_in_other_partition).
    if not host and _host_exists_in_other_partition(host_id, hostname):
        return True

    if not host:
        # Host is genuinely absent from every partition - send error response
        error_message = {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": _("Host with ID %s is not registered. Please re-register.")
            % host_id,
            "data": {"host_id": host_id},
        }
        await connection.send_message(error_message)
        return False
    return True
