# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    SINGLETON_FEDERATION_COORDINATOR_ID,
    FederationCoordinator,
)
from backend.services import federation_identity_service as identity_svc

# ---------------------------------------------------------------------
# Status constants (kept in lockstep with the site engine).
# ---------------------------------------------------------------------

STATUS_NOT_ENROLLED = "not_enrolled"  # row absent OR never enrolled
STATUS_PENDING = "pending"
STATUS_ENROLLED = "enrolled"
STATUS_SUSPENDED = "suspended"
STATUS_REMOVED = "removed"

# ---------------------------------------------------------------------
# Connection-health classification (Phase 12.2)
# ---------------------------------------------------------------------

CONN_ONLINE = "online"
CONN_DEGRADED = "degraded"
CONN_OFFLINE = "offline"
CONN_UNKNOWN = "unknown"

# How many *consecutive* failed sync attempts before the uplink is
# considered fully offline (and the site flips into local autonomy mode).
# Anything between 1 and this is "degraded" — a transient blip the operator
# usually shouldn't be paged about.
OFFLINE_AFTER_FAILURES = 3

# Reconnect backoff: after a failure the outbound tick must wait at least
# this long before contacting the coordinator again, doubling per
# consecutive failure up to the cap.  Keeps a hard-down coordinator from
# being hammered every ``sync_interval_seconds`` while still recovering
# quickly once it returns.
RECONNECT_BACKOFF_BASE_SECONDS = 30
RECONNECT_BACKOFF_CAP_SECONDS = 900  # 15 minutes


# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


class FederationCoordinatorError(Exception):
    """Base class for coordinator-service errors."""


class InvalidCoordinatorStateError(FederationCoordinatorError, ValueError):
    """Raised when the requested transition isn't valid for the current
    ``enrollment_status``.  Distinct from ``LookupError`` because the
    site code typically wants to surface this as a 409 not a 404."""


class CoordinatorIdentityProofError(FederationCoordinatorError, ValueError):
    """Raised when the coordinator fails strict out-of-band identity
    verification during enrollment — no coordinator identity key was
    pre-registered on this site, or the coordinator's Ed25519 proof didn't
    verify against it over the fetched TLS cert.  The site refuses to pin the
    cert (the engine maps this to a 401)."""


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _classify_connection(consecutive_failures: int) -> str:
    """Map a consecutive-failure count to a ``connection_state`` label."""
    if consecutive_failures <= 0:
        return CONN_ONLINE
    if consecutive_failures < OFFLINE_AFTER_FAILURES:
        return CONN_DEGRADED
    return CONN_OFFLINE


def _backoff_seconds(consecutive_failures: int) -> int:
    """Exponential reconnect backoff (base · 2^(failures-1)) capped.

    ``consecutive_failures`` is the post-increment count, so the first
    failure (count 1) waits ``base``; failures saturate at the cap rather
    than overflowing the shift.
    """
    if consecutive_failures <= 1:
        return RECONNECT_BACKOFF_BASE_SECONDS
    # Cap the exponent so 2**n can't blow up on a long outage.
    exponent = min(consecutive_failures - 1, 20)
    return min(
        RECONNECT_BACKOFF_BASE_SECONDS * (2**exponent),
        RECONNECT_BACKOFF_CAP_SECONDS,
    )


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
    coordinator_identity_public_key_pem: Optional[str] = None,
) -> FederationCoordinator:
    """Begin an enrollment with the named coordinator.

    Writes the coordinator's URL + pinned TLS cert into the singleton
    row and flips ``enrollment_status`` to ``pending``.  The actual
    token-exchange handshake against the coordinator happens at the
    engine layer; this helper just persists what the operator
    supplied.

    ``coordinator_identity_public_key_pem`` is the coordinator's Ed25519
    IDENTITY public key, exchanged OUT OF BAND and pasted in by the operator.
    It is the anchor :func:`verify_coordinator_identity_proof` checks the
    coordinator's enrollment proof against before the site pins the fetched
    cert — closing the enrollment-time MITM.  Required for strict enrollment;
    optional here only so a row can be staged before the key is supplied.

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
    if coordinator_identity_public_key_pem:
        # Fail fast on a malformed key rather than at the opaquer proof step.
        try:
            identity_svc.fingerprint_of_public_pem(coordinator_identity_public_key_pem)
        except ValueError as exc:
            raise ValueError(
                "coordinator_identity_public_key_pem is not a valid Ed25519 "
                "public key"
            ) from exc

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
    if coordinator_identity_public_key_pem:
        row.coordinator_identity_public_key_pem = coordinator_identity_public_key_pem
    row.sync_interval_seconds = sync_interval_seconds
    # Only flip status to ``pending`` when not already enrolled —
    # re-supplying the cert during an enrollment refresh shouldn't
    # demote a fully-enrolled site back to pending.
    if row.enrollment_status not in {STATUS_ENROLLED, STATUS_SUSPENDED}:
        row.enrollment_status = STATUS_PENDING
    return row


def verify_coordinator_identity_proof(
    session: Session,
    *,
    coordinator_tls_cert_pem: str,
    identity_proof_b64: Optional[str],
) -> bool:
    """Strictly verify the coordinator's enrollment identity proof.

    Returns ``True`` only when the coordinator's pre-registered (out-of-band)
    identity key signed exactly ``coordinator_tls_cert_pem``.  ``False`` when no
    coordinator identity key was registered on this site, the proof is missing,
    or it doesn't verify — in which case the site engine must abort enrollment
    and NOT pin the fetched cert.  The site engine calls this after fetching the
    coordinator's cert + proof and before :func:`mark_enrolled`."""
    row = get_coordinator(session)
    if row is None or not row.coordinator_identity_public_key_pem:
        return False
    return identity_svc.verify_enrollment_proof(
        role="coordinator",
        tls_cert_pem=coordinator_tls_cert_pem,
        signature_b64=identity_proof_b64 or "",
        peer_identity_public_pem=row.coordinator_identity_public_key_pem,
    )


def mark_enrolled(
    session: Session,
    *,
    site_id: Any,
    site_tls_cert_pem: str,
    sync_bearer_token: Optional[str] = None,
    coordinator_inbound_bearer_token_hash: Optional[str] = None,
) -> FederationCoordinator:
    """Record a successful handshake response from the coordinator.

    The coordinator assigns this site a ``site_id`` UUID — that's
    what every upstream sync payload carries.  The coordinator also
    pins the site's TLS cert (for the reverse direction of the mTLS
    handshake); we store the same cert here so the site engine can
    surface it in diagnostics.

    Phase 12.10 Slice 2: ``sync_bearer_token`` is the long-lived
    plaintext bearer the coordinator returns from its
    ``complete_enrollment`` response.  The site stores it here so
    the outbound tick worker can present it on every sync POST.

    Phase 12.10 Slice 3: ``coordinator_inbound_bearer_token_hash`` is
    the SHA-256 of the bearer the COORDINATOR will present on every
    push into this site.  The plaintext lives on the coordinator
    (it's the sender for that direction); the site only needs the
    hash to verify incoming ``/site/policies`` and ``/site/commands``
    POSTs.

    Both bearer kwargs are optional only so existing test fixtures
    that pre-date these columns don't break; production callers
    should always supply both.

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
    if sync_bearer_token is not None:
        row.sync_bearer_token = sync_bearer_token
    if coordinator_inbound_bearer_token_hash is not None:
        row.coordinator_inbound_bearer_token_hash = (
            coordinator_inbound_bearer_token_hash
        )
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

    Wipes the coordinator URL + cert pin + site_id + sync bearer.
    Used when an operator wants to migrate this site to a different
    coordinator, or when a re-enrollment is needed after
    ``mark_removed``.  The bearer scrub is critical — a stale bearer
    pointed at a former coordinator would otherwise keep firing on
    every tick.
    """
    row = _get_or_create(session)
    row.coordinator_url = None
    row.coordinator_tls_cert_pem = None
    row.site_id = None
    row.site_tls_cert_pem = None
    row.sync_bearer_token = None
    row.coordinator_inbound_bearer_token_hash = None
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
    """Mark that we just attempted an upstream sync, updating uplink health.

    Updates ``last_sync_at`` / ``last_sync_status`` (the most recent
    *attempt*) and, on success, ``last_successful_sync_at`` (the most
    recent *success* — survives a run of failures so the UI can show "no
    contact for 2h").  Maintains ``consecutive_sync_failures``, the derived
    ``connection_state`` (online / degraded / offline), and the
    ``next_reconnect_at`` backoff gate.

    On success the failure counter resets to 0, the state goes ``online``,
    and the backoff gate clears.  On failure the counter increments, the
    state is reclassified, and the gate is pushed out by an exponential
    backoff so a hard-down coordinator isn't hammered every interval.
    """
    row = _get_or_create(session)
    now = _utcnow_naive()
    row.last_sync_at = now
    row.last_sync_status = "success" if success else (error or "error")
    row.last_sync_error = None if success else error

    if success:
        row.consecutive_sync_failures = 0
        row.last_successful_sync_at = now
        row.connection_state = CONN_ONLINE
        row.next_reconnect_at = None
    else:
        row.consecutive_sync_failures = (row.consecutive_sync_failures or 0) + 1
        row.connection_state = _classify_connection(row.consecutive_sync_failures)
        row.next_reconnect_at = now + timedelta(
            seconds=_backoff_seconds(row.consecutive_sync_failures)
        )
    return row


# ---------------------------------------------------------------------
# Connection health + local autonomy (read/decision side)
# ---------------------------------------------------------------------


def should_attempt_sync(
    session: Session,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Whether the outbound tick may contact the coordinator right now.

    Implements the reconnect backoff: returns False while
    ``next_reconnect_at`` is in the future, so the tick skips the network
    round-trip (it still drains/queues locally) until the gate opens.  A
    site that has never failed (gate is NULL) always returns True.

    The site must also be enrolled (or suspended — a suspended site still
    polls so it learns when the coordinator resumes it); ``pending`` /
    ``removed`` / ``not_enrolled`` short-circuit to False.
    """
    row = get_coordinator(session)
    if row is None:
        return False
    if row.enrollment_status not in {STATUS_ENROLLED, STATUS_SUSPENDED}:
        return False
    if row.next_reconnect_at is None:
        return True
    now = now or _utcnow_naive()
    return now >= row.next_reconnect_at


def is_autonomous(session: Session) -> bool:
    """True iff the site is enrolled but currently cut off from its
    coordinator (``connection_state == offline``).

    In this state the site runs in *local autonomy mode*: agents keep
    reporting, OS upgrades keep running, and local deltas keep queuing in
    ``federation_sync_queue`` for replay once the uplink recovers — nothing
    blocks on the coordinator.  The flag exists so the UI can show an
    "operating independently" banner and the engine can suppress
    coordinator-dependent actions.
    """
    row = get_coordinator(session)
    return (
        row is not None
        and row.enrollment_status == STATUS_ENROLLED
        and row.connection_state == CONN_OFFLINE
    )


def connection_health(session: Session) -> dict:
    """Snapshot of the site's uplink health for the sync-status surface.

    Returns a plain dict (not the ORM row) so the engine router and the
    OSS stub can both emit it without leaking SQLAlchemy objects.  Shape is
    stable regardless of enrollment: an unenrolled site reports
    ``state == unknown`` with null timestamps.
    """
    row = get_coordinator(session)
    if row is None:
        return {
            "state": CONN_UNKNOWN,
            "enrolled": False,
            "autonomous": False,
            "consecutive_failures": 0,
            "last_sync_at": None,
            "last_successful_sync_at": None,
            "last_sync_status": None,
            "last_sync_error": None,
            "next_reconnect_at": None,
        }
    enrolled = row.enrollment_status == STATUS_ENROLLED
    return {
        "state": row.connection_state or CONN_UNKNOWN,
        "enrolled": enrolled,
        "autonomous": enrolled and row.connection_state == CONN_OFFLINE,
        "consecutive_failures": row.consecutive_sync_failures or 0,
        "last_sync_at": row.last_sync_at,
        "last_successful_sync_at": row.last_successful_sync_at,
        "last_sync_status": row.last_sync_status,
        "last_sync_error": row.last_sync_error,
        "next_reconnect_at": row.next_reconnect_at,
    }
