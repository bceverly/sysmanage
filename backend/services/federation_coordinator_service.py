"""
Site-side coordinator-connection service (Phase 12.2).

Manages the singleton ``federation_coordinator`` row that records
this site's connection details to its coordinator.  Mirrors the
shape of ``federation_site_service`` on the coordinator side: pure
Python service layer that the Pro+ ``federation_site_engine``
wraps as router handlers.

The federation_coordinator table has a fixed primary key
(``SINGLETON_FEDERATION_COORDINATOR_ID``) — every helper here
upserts the same row, mirroring the MFA / mirror-settings pattern.

State machine for ``enrollment_status``:
  pending    → start_enrollment() set this on first call
  enrolled   → mark_enrolled() after coordinator confirms handshake
  suspended  → coordinator suspended us; we keep accepting agents
               locally but stop pushing upstream
  removed    → coordinator removed our enrollment (terminal)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    SINGLETON_FEDERATION_COORDINATOR_ID,
    FederationCoordinator,
)

# ---------------------------------------------------------------------
# Status constants (kept in lockstep with the site engine).
# ---------------------------------------------------------------------

STATUS_NOT_ENROLLED = "not_enrolled"  # row absent OR never enrolled
STATUS_PENDING = "pending"
STATUS_ENROLLED = "enrolled"
STATUS_SUSPENDED = "suspended"
STATUS_REMOVED = "removed"


# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


class FederationCoordinatorError(Exception):
    """Base class for coordinator-service errors."""


class InvalidCoordinatorStateError(FederationCoordinatorError, ValueError):
    """Raised when the requested transition isn't valid for the current
    ``enrollment_status``.  Distinct from ``LookupError`` because the
    site code typically wants to surface this as a 409 not a 404."""


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_or_create(session: Session) -> FederationCoordinator:
    """Fetch the singleton row, creating it (in ``not_enrolled`` shape)
    if it doesn't yet exist.

    Called by every mutating helper so callers don't have to first
    check "is there a row".  The row's PK is the well-known
    ``SINGLETON_FEDERATION_COORDINATOR_ID`` constant.
    """
    row = session.get(FederationCoordinator, SINGLETON_FEDERATION_COORDINATOR_ID)
    if row is None:
        row = FederationCoordinator(
            id=SINGLETON_FEDERATION_COORDINATOR_ID,
            enrollment_status=STATUS_PENDING,
        )
        session.add(row)
        session.flush()
    return row


# ---------------------------------------------------------------------
# Read-side
# ---------------------------------------------------------------------


def get_coordinator(session: Session) -> Optional[FederationCoordinator]:
    """Return the coordinator row, or ``None`` if no enrollment has
    ever been started on this site.

    Read-only — does NOT create the row.  Use this for "is this site
    federated at all?" probes (e.g. the OSS site engine's startup
    check before kicking off the sync worker).
    """
    return session.get(FederationCoordinator, SINGLETON_FEDERATION_COORDINATOR_ID)


def is_enrolled(session: Session) -> bool:
    """Convenience: True iff the site has completed enrollment with
    its coordinator and isn't currently suspended/removed."""
    row = get_coordinator(session)
    return row is not None and row.enrollment_status == STATUS_ENROLLED


# ---------------------------------------------------------------------
# Enrollment lifecycle
# ---------------------------------------------------------------------


def start_enrollment(
    session: Session,
    *,
    coordinator_url: str,
    coordinator_tls_cert_pem: str,
    sync_interval_seconds: int = 300,
) -> FederationCoordinator:
    """Begin an enrollment with the named coordinator.

    Writes the coordinator's URL + pinned TLS cert into the singleton
    row and flips ``enrollment_status`` to ``pending``.  The actual
    token-exchange handshake against the coordinator happens at the
    engine layer; this helper just persists what the operator
    supplied.

    Idempotent on the input — re-calling with the same coordinator
    URL is fine and just refreshes the cert.  But re-calling with a
    DIFFERENT URL when already enrolled to a different coordinator
    raises :class:`InvalidCoordinatorStateError` (you can't be
    federated under two coordinators at once).
    """
    if not coordinator_url or not coordinator_url.strip():
        raise ValueError("coordinator_url is required")
    if not coordinator_tls_cert_pem:
        raise ValueError("coordinator_tls_cert_pem is required")
    if sync_interval_seconds <= 0:
        raise ValueError("sync_interval_seconds must be > 0")

    coordinator_url = coordinator_url.strip()
    row = _get_or_create(session)

    if (
        row.enrollment_status == STATUS_ENROLLED
        and row.coordinator_url
        and row.coordinator_url != coordinator_url
    ):
        raise InvalidCoordinatorStateError(
            f"Already enrolled with coordinator '{row.coordinator_url}'; "
            f"call clear_enrollment first before switching coordinators."
        )

    row.coordinator_url = coordinator_url
    row.coordinator_tls_cert_pem = coordinator_tls_cert_pem
    row.sync_interval_seconds = sync_interval_seconds
    # Only flip status to ``pending`` when not already enrolled —
    # re-supplying the cert during an enrollment refresh shouldn't
    # demote a fully-enrolled site back to pending.
    if row.enrollment_status not in {STATUS_ENROLLED, STATUS_SUSPENDED}:
        row.enrollment_status = STATUS_PENDING
    return row


def mark_enrolled(
    session: Session,
    *,
    site_id: Any,
    site_tls_cert_pem: str,
) -> FederationCoordinator:
    """Record a successful handshake response from the coordinator.

    The coordinator assigns this site a ``site_id`` UUID — that's
    what every upstream sync payload carries.  The coordinator also
    pins the site's TLS cert (for the reverse direction of the mTLS
    handshake); we store the same cert here so the site engine can
    surface it in diagnostics.

    Only valid against ``pending`` or ``suspended``.  ``suspended``
    → ``enrolled`` is the resume path after a coordinator-side
    ``resume_site``.
    """
    if not site_tls_cert_pem:
        raise ValueError("site_tls_cert_pem is required")
    row = _get_or_create(session)
    if row.enrollment_status not in {STATUS_PENDING, STATUS_SUSPENDED}:
        raise InvalidCoordinatorStateError(
            f"Cannot mark enrolled from status '{row.enrollment_status}'"
        )
    row.site_id = site_id
    row.site_tls_cert_pem = site_tls_cert_pem
    row.enrollment_status = STATUS_ENROLLED
    row.enrolled_at = _utcnow_naive()
    return row


def mark_suspended(session: Session) -> FederationCoordinator:
    """Coordinator suspended this site.

    The site server stays operational locally — agents continue
    reporting, OS upgrades continue running — but the sync worker
    stops draining the upstream queue.  Called by the site engine
    when the coordinator's policy-pull endpoint reports our status
    as ``suspended``.
    """
    row = _get_or_create(session)
    if row.enrollment_status != STATUS_ENROLLED:
        raise InvalidCoordinatorStateError(
            f"Can only suspend from 'enrolled' (currently "
            f"'{row.enrollment_status}')"
        )
    row.enrollment_status = STATUS_SUSPENDED
    return row


def mark_removed(session: Session) -> FederationCoordinator:
    """Coordinator removed this site's enrollment.

    Terminal.  The site server can be re-enrolled via a fresh
    ``start_enrollment`` flow if the operator wants — that's what
    ``clear_enrollment`` is for; calling this just records the
    coordinator's verdict.
    """
    row = _get_or_create(session)
    row.enrollment_status = STATUS_REMOVED
    return row


def clear_enrollment(session: Session) -> FederationCoordinator:
    """Reset the singleton row so a fresh enrollment can begin.

    Wipes the coordinator URL + cert pin + site_id.  Used when an
    operator wants to migrate this site to a different coordinator,
    or when a re-enrollment is needed after ``mark_removed``.
    """
    row = _get_or_create(session)
    row.coordinator_url = None
    row.coordinator_tls_cert_pem = None
    row.site_id = None
    row.site_tls_cert_pem = None
    row.enrolled_at = None
    row.last_sync_at = None
    row.last_sync_status = None
    row.last_sync_error = None
    row.enrollment_status = STATUS_PENDING
    return row


# ---------------------------------------------------------------------
# Sync-status updates (called from the site engine's sync worker)
# ---------------------------------------------------------------------


def record_sync_attempt(
    session: Session,
    *,
    success: bool,
    error: Optional[str] = None,
) -> FederationCoordinator:
    """Mark that we just attempted an upstream sync.

    Updates ``last_sync_at`` and ``last_sync_status``; on failure
    records the error string so the operator can see it on the
    sync-status dashboard without scraping logs.
    """
    row = _get_or_create(session)
    row.last_sync_at = _utcnow_naive()
    row.last_sync_status = "success" if success else (error or "error")
    row.last_sync_error = None if success else error
    return row
