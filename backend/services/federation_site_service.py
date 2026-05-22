"""
Federation site-registry service (Phase 12.1.B).

Pure-Python service layer for the coordinator-side ``federation_sites``
table.  The Pro+ ``federation_controller_engine`` Cython module imports
these helpers and wraps them in FastAPI route handlers; the OSS half
provides the actual SQLAlchemy operations + validation + audit-trail
side effects.  Keeping the logic in OSS means:

  * Tests run against the real models (no Cython mocking gymnastics).
  * 12.1.D (rollup ingestion) and 12.4 (access-groups migration) can
    reuse the same site lookup / audit helpers without re-implementing.
  * Future cross-engine consumers (a CLI, a webhook handler, etc.) can
    import these without depending on FastAPI.

This module deliberately raises plain exceptions (``ValueError``,
``LookupError``) rather than ``HTTPException``.  Routing-layer error
mapping is the engine's job — keeping HTTP concerns out of the
service layer lets non-FastAPI callers use it too.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    FederationAuditLog,
    FederationSite,
)

# ---------------------------------------------------------------------
# Status constants (kept in lockstep with the database column values
# the model writes via ``server_default``).  Centralizing these here
# means callers don't sprinkle string literals across the codebase
# and a future rename is a one-line change.
# ---------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_ENROLLED = "enrolled"
STATUS_SUSPENDED = "suspended"
STATUS_REMOVED = "removed"

# Operations recorded in ``federation_audit_log.operation``.  The
# engine reads these constants too, so a typo here would fan out to
# audit-search consumers — defined here as the single source of truth.
AUDIT_OP_SITE_ENROLLMENT_STARTED = "site_enrollment_started"
AUDIT_OP_SITE_ENROLLMENT_COMPLETED = "site_enrollment_completed"
AUDIT_OP_SITE_ENROLLMENT_CANCELLED = "site_enrollment_cancelled"  # 12.1.C
AUDIT_OP_SITE_TOKEN_REGENERATED = "site_token_regenerated"  # nosec B105 - audit operation name constant, not a credential  # 12.1.C
AUDIT_OP_SITE_UPDATED = "site_updated"
AUDIT_OP_SITE_SUSPENDED = "site_suspended"
AUDIT_OP_SITE_RESUMED = "site_resumed"
AUDIT_OP_SITE_REMOVED = "site_removed"

# Phase 12.1.C: default enrollment-token lifetime.  24 h gives the
# operator a generous window to deliver the token to the site server
# (chat, ticket, secret manager) but short enough that a leaked token
# isn't useful indefinitely.  Operators can override per-call.
DEFAULT_ENROLLMENT_TOKEN_TTL_HOURS = 24


# ---------------------------------------------------------------------
# Exceptions — service-layer specific, mapped to HTTP codes at the
# router edge (in the Pro+ engine).
# ---------------------------------------------------------------------


class FederationSiteError(Exception):
    """Base class for site-service errors."""


class SiteNotFoundError(FederationSiteError, LookupError):
    """Raised when a site_id / name doesn't resolve to an existing row."""


class SiteNameConflictError(FederationSiteError, ValueError):
    """Raised when a name is already taken by another (non-removed) site."""


class InvalidEnrollmentTokenError(FederationSiteError, ValueError):
    """Raised when a presented enrollment token doesn't match any pending site."""


class EnrollmentTokenExpiredError(FederationSiteError, ValueError):
    """Raised when a token matches a pending site but its TTL has elapsed.

    Distinct from :class:`InvalidEnrollmentTokenError` so the router can
    show "token expired, ask an admin to regenerate" instead of the
    less-actionable "no such token" — the operator path differs.
    """


class InvalidSiteStateError(FederationSiteError, ValueError):
    """Raised when a state transition isn't valid (e.g. resuming an
    already-enrolled site, suspending a removed site).  Distinct from
    ``SiteNotFoundError`` so the router can map this to 409 vs 404."""


# ---------------------------------------------------------------------
# Enrollment token helpers
# ---------------------------------------------------------------------


# 32-byte URL-safe token = 256 bits of entropy; ample for an
# enrollment secret that's only valid for the brief window between
# operator generation and site exchange.
_TOKEN_BYTES = 32


def generate_enrollment_token() -> Tuple[str, str]:
    """Return ``(plaintext_token, sha256_hash_hex)``.

    The plaintext is what the operator hands to the site server; the
    hash is what we store in ``federation_sites.enrollment_token_hash``
    so the plaintext never lives in the DB.  Comparison at completion
    time is constant-time.
    """
    plaintext = secrets.token_urlsafe(_TOKEN_BYTES)
    sha256_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return plaintext, sha256_hash


def _hash_token(plaintext: str) -> str:
    """Hash a plaintext enrollment token the same way ``generate_enrollment_token`` does."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_sync_bearer_token() -> Tuple[str, str]:
    """Return ``(plaintext_token, sha256_hash_hex)`` for the long-lived
    site → coordinator sync bearer.

    Distinct from ``generate_enrollment_token`` even though the
    cryptographic shape is identical — keeping the helpers separate
    makes the lifecycle distinction grep-able (enrollment tokens are
    one-shot, sync bearers are long-lived) and lets us evolve them
    independently (e.g., different entropy budgets, different
    rotation policies).
    """
    plaintext = secrets.token_urlsafe(_TOKEN_BYTES)
    sha256_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return plaintext, sha256_hash


def generate_coordinator_outbound_bearer_token() -> str:
    """Return a fresh plaintext bearer for the coordinator → site
    direction.

    The coordinator stores the plaintext (it's the SENDER for this
    direction).  Only the SHA-256 is shipped to the site at enrollment
    time, where the site keeps it in
    ``federation_coordinator.coordinator_inbound_bearer_token_hash``
    for verifying incoming push calls.
    """
    return secrets.token_urlsafe(_TOKEN_BYTES)


def find_site_by_sync_bearer_token(
    session: Session, plaintext_token: str
) -> Optional[FederationSite]:
    """Resolve a presented sync bearer token to its owning site row.

    Returns ``None`` if no site matches, the site is not in
    ``status='enrolled'``, or the token is empty.  Callers (the engine's
    FastAPI dependency) translate the ``None`` into HTTP 401.

    The lookup is by hash equality on the indexed token column — no
    plaintext comparison ever touches the DB.
    """
    if not plaintext_token:
        return None
    expected_hash = _hash_token(plaintext_token)
    return (
        session.execute(
            select(FederationSite).where(
                and_(
                    FederationSite.sync_bearer_token_hash == expected_hash,
                    FederationSite.status == STATUS_ENROLLED,
                )
            )
        )
        .scalars()
        .first()
    )


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _utcnow_naive() -> datetime:
    """UTC ``now()`` with tzinfo stripped — matches the model defaults."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _coerce_uuid(value: Any) -> UUID:
    """Accept a UUID or its string representation.  Raises ValueError
    on garbage — the router maps that to 400."""
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise ValueError(f"Expected UUID or str, got {type(value).__name__}")


def _ensure_site(session: Session, site_id: Any) -> FederationSite:
    """Look up a site by id, raise :class:`SiteNotFoundError` if missing.

    Used as the first call in every mutating operation so the actual
    UPDATE / SELECT doesn't have to repeat the existence check.
    """
    uid = _coerce_uuid(site_id)
    site = session.get(FederationSite, uid)
    if site is None:
        raise SiteNotFoundError(f"No federation site with id={uid}")
    return site


def _log_audit(
    session: Session,
    operation: str,
    *,
    actor_userid: Optional[str] = None,
    target_site_id: Optional[Any] = None,
    details: Optional[Dict[str, Any]] = None,
) -> FederationAuditLog:
    """Append one row to ``federation_audit_log``.

    Internal because callers use the higher-level ``create_site`` /
    ``suspend_site`` / ... functions which already audit.  Exposed
    indirectly: 12.1.D rollup ingestion will call ``_log_audit``
    directly for ``rollup_received`` entries, so the function is
    importable from this module's public surface (no underscore in
    the name despite being internal-by-convention).
    """
    import json  # noqa: PLC0415

    entry = FederationAuditLog(
        operation=operation,
        actor_userid=actor_userid,
        target_site_id=(
            _coerce_uuid(target_site_id) if target_site_id is not None else None
        ),
        details_json=json.dumps(details) if details else None,
    )
    session.add(entry)
    return entry


# ---------------------------------------------------------------------
# Public CRUD surface
# ---------------------------------------------------------------------


def create_site(
    session: Session,
    *,
    name: str,
    url: str,
    location_label: Optional[str] = None,
    sync_interval_seconds: int = 300,
    agent_version_min: Optional[str] = None,
    geo_latitude: Optional[float] = None,
    geo_longitude: Optional[float] = None,
    geo_country_code: Optional[str] = None,
    actor_userid: Optional[str] = None,
    token_ttl_hours: int = DEFAULT_ENROLLMENT_TOKEN_TTL_HOURS,
) -> Tuple[FederationSite, str]:
    """Register a new site in the coordinator registry.

    Generates an enrollment token (plaintext returned to the caller,
    hash stored on the row), records its expiry timestamp, sets
    ``status='pending'`` until the site completes enrollment, and
    writes a ``site_enrollment_started`` audit entry.

    Returns ``(site, plaintext_enrollment_token)``.  The plaintext is
    delivered to the operator out-of-band (UI download, CLI output);
    it cannot be recovered from the database after this call.
    """
    if not name or not name.strip():
        raise ValueError("Site name is required")
    if not url or not url.strip():
        raise ValueError("Site url is required")
    if token_ttl_hours <= 0:
        raise ValueError("token_ttl_hours must be > 0")

    # Uniqueness check on name (across non-removed sites).  The
    # ``unique=True`` constraint on the column catches collisions at
    # the DB level too, but raising the clearer error here avoids the
    # less-friendly IntegrityError surface.
    name = name.strip()
    existing = (
        session.execute(select(FederationSite).where(FederationSite.name == name))
        .scalars()
        .first()
    )
    if existing is not None:
        raise SiteNameConflictError(
            f"A federation site named '{name}' already exists "
            f"(status={existing.status})"
        )

    plaintext, token_hash = generate_enrollment_token()
    site = FederationSite(
        name=name,
        url=url.strip(),
        location_label=location_label,
        enrollment_token_hash=token_hash,
        enrollment_token_expires_at=_utcnow_naive() + timedelta(hours=token_ttl_hours),
        status=STATUS_PENDING,
        sync_interval_seconds=sync_interval_seconds,
        agent_version_min=agent_version_min,
        geo_latitude=geo_latitude,
        geo_longitude=geo_longitude,
        geo_country_code=geo_country_code,
    )
    session.add(site)
    session.flush()  # populate ``site.id`` for the audit row's FK

    _log_audit(
        session,
        AUDIT_OP_SITE_ENROLLMENT_STARTED,
        actor_userid=actor_userid,
        target_site_id=site.id,
        details={
            "name": site.name,
            "url": site.url,
            "location_label": site.location_label,
            "token_ttl_hours": token_ttl_hours,
        },
    )
    return site, plaintext


def complete_enrollment(
    session: Session,
    *,
    plaintext_token: str,
    tls_cert_pem: str,
    actor_userid: Optional[str] = None,
) -> Tuple[FederationSite, str, str]:
    """Finalise a pending site enrollment.

    Looks up the pending site by hashed token (NOT by id — the site
    presents the token over the network, not the site_id), checks
    the token hasn't expired, records the site's TLS certificate for
    future mTLS pinning, mints BOTH directional bearers (Phase 12.10
    Slice 1 + Slice 3), flips ``status`` to ``enrolled``, stamps
    ``enrolled_at``, and scrubs the enrollment token hash so it
    can't be replayed.

    Returns ``(site, plaintext_sync_bearer_token,
    plaintext_coordinator_outbound_bearer_token_for_hashing)``:

      * The sync bearer (site → coordinator) is returned as plaintext
        for the site server to STORE.  The coordinator only retains
        the SHA-256 hash on the row.
      * The coordinator-outbound bearer (coordinator → site) is
        returned as plaintext SOLELY so the caller can SHA-256 it for
        delivery to the site.  The coordinator persists the PLAINTEXT
        on the site row (it's the sender for that direction); the
        site stores only the hash for verifying incoming pushes.

    Caller responsibility: in the HTTP response, ship
    ``sync_bearer_token`` (plaintext) and
    ``coordinator_inbound_bearer_token_hash`` (SHA-256 of the third
    return value) to the site.  Never let the coordinator-outbound
    plaintext leave the coordinator.
    """
    if not plaintext_token:
        raise InvalidEnrollmentTokenError("Empty enrollment token")
    if not tls_cert_pem:
        raise ValueError("Site TLS certificate is required")

    expected_hash = _hash_token(plaintext_token)
    site = (
        session.execute(
            select(FederationSite).where(
                and_(
                    FederationSite.enrollment_token_hash == expected_hash,
                    FederationSite.status == STATUS_PENDING,
                )
            )
        )
        .scalars()
        .first()
    )
    if site is None:
        raise InvalidEnrollmentTokenError(
            "No pending site matches the presented enrollment token"
        )

    # TTL check.  A legitimate-but-stale token must surface as a
    # distinct error so the operator gets a "ask admin to regenerate"
    # message instead of "unknown token, check the value".
    if (
        site.enrollment_token_expires_at is not None
        and site.enrollment_token_expires_at < _utcnow_naive()
    ):
        raise EnrollmentTokenExpiredError(
            f"Enrollment token for site '{site.name}' expired at "
            f"{site.enrollment_token_expires_at.isoformat()}"
        )

    site.tls_cert_pem = tls_cert_pem
    site.enrollment_token_hash = None  # scrub
    site.enrollment_token_expires_at = None
    site.enrolled_at = _utcnow_naive()
    site.status = STATUS_ENROLLED

    # Mint BOTH directional bearers.  Same one-shot semantics as the
    # enrollment token: plaintext returns to the caller exactly once;
    # what we persist depends on direction.
    plaintext_sync_bearer, sync_bearer_hash = generate_sync_bearer_token()
    site.sync_bearer_token_hash = sync_bearer_hash

    # Phase 12.10 Slice 3 — coordinator → site direction.  The
    # coordinator IS the sender, so we keep the plaintext on the
    # row.  The caller HASHES this and ships the hash to the site.
    coord_outbound_plaintext = generate_coordinator_outbound_bearer_token()
    site.coordinator_outbound_bearer_token = coord_outbound_plaintext

    _log_audit(
        session,
        AUDIT_OP_SITE_ENROLLMENT_COMPLETED,
        actor_userid=actor_userid,
        target_site_id=site.id,
        details={"name": site.name, "url": site.url},
    )
    return site, plaintext_sync_bearer, coord_outbound_plaintext


def cancel_enrollment(
    session: Session,
    site_id: Any,
    *,
    actor_userid: Optional[str] = None,
) -> FederationSite:
    """Abort a pending enrollment.

    Scrubs the outstanding token (so the would-be site can't complete
    enrollment after the operator cancels) and soft-removes the row
    so the audit trail survives.  Only valid against
    ``status='pending'``; calling on an already-enrolled site is the
    job of :func:`remove_site` instead.
    """
    site = _ensure_site(session, site_id)
    if site.status != STATUS_PENDING:
        raise InvalidSiteStateError(
            f"Site {site.id} status is '{site.status}'; cancel_enrollment "
            f"only applies to pending sites — use remove_site / suspend_site "
            f"for an enrolled site."
        )
    site.enrollment_token_hash = None
    site.enrollment_token_expires_at = None
    site.status = STATUS_REMOVED
    _log_audit(
        session,
        AUDIT_OP_SITE_ENROLLMENT_CANCELLED,
        actor_userid=actor_userid,
        target_site_id=site.id,
        details={"name": site.name},
    )
    return site


def regenerate_enrollment_token(
    session: Session,
    site_id: Any,
    *,
    token_ttl_hours: int = DEFAULT_ENROLLMENT_TOKEN_TTL_HOURS,
    actor_userid: Optional[str] = None,
) -> Tuple[FederationSite, str]:
    """Replace a pending site's enrollment token with a fresh one.

    Use case: operator generated a token, lost / leaked / let it
    expire it, and needs a new one without re-running ``create_site``
    (which would lose any UI-side state like the site name).

    Returns ``(site, plaintext_enrollment_token)``.  Only valid
    against ``status='pending'``.
    """
    if token_ttl_hours <= 0:
        raise ValueError("token_ttl_hours must be > 0")
    site = _ensure_site(session, site_id)
    if site.status != STATUS_PENDING:
        raise InvalidSiteStateError(
            f"Site {site.id} status is '{site.status}'; can only regenerate "
            f"a token for a pending site."
        )
    plaintext, token_hash = generate_enrollment_token()
    site.enrollment_token_hash = token_hash
    site.enrollment_token_expires_at = _utcnow_naive() + timedelta(
        hours=token_ttl_hours
    )
    _log_audit(
        session,
        AUDIT_OP_SITE_TOKEN_REGENERATED,
        actor_userid=actor_userid,
        target_site_id=site.id,
        details={"token_ttl_hours": token_ttl_hours},
    )
    return site, plaintext


def get_site(session: Session, site_id: Any) -> FederationSite:
    """Fetch a site by id.  Raises :class:`SiteNotFoundError` if missing."""
    return _ensure_site(session, site_id)


def get_site_by_name(session: Session, name: str) -> Optional[FederationSite]:
    """Fetch a site by name, or ``None`` if no row matches.

    Unlike ``get_site``, returns None instead of raising — name
    lookups are often used as "does this exist?" predicates by the UI.
    """
    if not name:
        return None
    return (
        session.execute(select(FederationSite).where(FederationSite.name == name))
        .scalars()
        .first()
    )


def list_sites(
    session: Session,
    *,
    status: Optional[str] = None,
    include_removed: bool = False,
    limit: Optional[int] = None,
) -> List[FederationSite]:
    """List sites, optionally filtered by status.

    By default removed sites are excluded so the Sites page doesn't
    show tombstones; passing ``include_removed=True`` overrides that
    (for audit views).
    """
    stmt = select(FederationSite)
    if status is not None:
        stmt = stmt.where(FederationSite.status == status)
    elif not include_removed:
        stmt = stmt.where(FederationSite.status != STATUS_REMOVED)
    stmt = stmt.order_by(FederationSite.name)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.execute(stmt).scalars().all())


# Subset of FederationSite columns that ``update_site`` will accept.
# Anything else passed in **fields is rejected — prevents the engine
# from accidentally letting a user PATCH the enrollment token hash
# or status (those have dedicated functions).
_UPDATABLE_FIELDS = frozenset(
    {
        "name",
        "url",
        "location_label",
        "sync_interval_seconds",
        "agent_version_min",
        "geo_latitude",
        "geo_longitude",
        "geo_country_code",
    }
)


def update_site(
    session: Session,
    site_id: Any,
    *,
    actor_userid: Optional[str] = None,
    **fields: Any,
) -> FederationSite:
    """Patch metadata fields on a site.

    Only the columns in ``_UPDATABLE_FIELDS`` are accepted; anything
    else raises ``ValueError``.  Status transitions go through
    ``suspend_site`` / ``resume_site`` / ``remove_site``; the
    enrollment token is managed by ``complete_enrollment``.
    """
    site = _ensure_site(session, site_id)
    if site.status == STATUS_REMOVED:
        raise InvalidSiteStateError(f"Cannot update a removed site (id={site.id})")

    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Unknown / non-updatable site fields: {sorted(unknown)}")

    # Special: name uniqueness when changing it.
    if "name" in fields and fields["name"] != site.name:
        if get_site_by_name(session, fields["name"]) is not None:
            raise SiteNameConflictError(
                f"A federation site named '{fields['name']}' already exists"
            )

    changes: Dict[str, Any] = {}
    for key, value in fields.items():
        if getattr(site, key) != value:
            setattr(site, key, value)
            changes[key] = value

    if changes:
        _log_audit(
            session,
            AUDIT_OP_SITE_UPDATED,
            actor_userid=actor_userid,
            target_site_id=site.id,
            details={"changes": changes},
        )
    return site


def _transition_status(
    session: Session,
    site_id: Any,
    *,
    expected_current: List[str],
    new_status: str,
    audit_op: str,
    actor_userid: Optional[str],
) -> FederationSite:
    """Shared state-machine logic for suspend/resume/remove.

    Raises :class:`InvalidSiteStateError` if the site's current
    status isn't in ``expected_current`` — keeps the per-transition
    public functions DRY without scattering business logic.
    """
    site = _ensure_site(session, site_id)
    if site.status not in expected_current:
        raise InvalidSiteStateError(
            f"Site {site.id} status is '{site.status}'; cannot transition "
            f"to '{new_status}' (expected one of {expected_current})"
        )
    site.status = new_status
    _log_audit(
        session,
        audit_op,
        actor_userid=actor_userid,
        target_site_id=site.id,
        details={"previous_status": expected_current, "new_status": new_status},
    )
    return site


def suspend_site(
    session: Session,
    site_id: Any,
    *,
    actor_userid: Optional[str] = None,
) -> FederationSite:
    """Mark an enrolled site as suspended.

    Suspended sites stay enrolled (the coordinator's TLS cert pin
    remains valid) but the coordinator stops accepting their upstream
    sync and refuses to dispatch new commands to them.  Used when an
    admin needs to temporarily quarantine a site without re-enrolling
    it later.
    """
    return _transition_status(
        session,
        site_id,
        expected_current=[STATUS_ENROLLED],
        new_status=STATUS_SUSPENDED,
        audit_op=AUDIT_OP_SITE_SUSPENDED,
        actor_userid=actor_userid,
    )


def resume_site(
    session: Session,
    site_id: Any,
    *,
    actor_userid: Optional[str] = None,
) -> FederationSite:
    """Lift a suspension and accept sync from the site again."""
    return _transition_status(
        session,
        site_id,
        expected_current=[STATUS_SUSPENDED],
        new_status=STATUS_ENROLLED,
        audit_op=AUDIT_OP_SITE_RESUMED,
        actor_userid=actor_userid,
    )


def remove_site(
    session: Session,
    site_id: Any,
    *,
    actor_userid: Optional[str] = None,
) -> FederationSite:
    """Soft-remove a site (sets ``status='removed'``).

    The row is preserved so the federation audit log can still
    resolve historical references by ``site_id``.  Cascade-DELETE on
    every child table (host_directory, rollups, audit log entries,
    policy assignments) is intentionally NOT triggered — operators
    can still inspect past activity for a removed site.

    Acceptable from any state except ``removed`` (no-op on already-
    removed sites — idempotent).
    """
    site = _ensure_site(session, site_id)
    if site.status == STATUS_REMOVED:
        return site  # idempotent
    previous_status = site.status
    site.status = STATUS_REMOVED
    # Scrub all live credentials.  Removed sites can't authenticate
    # in EITHER direction:
    #   * ``enrollment_token_hash``: enrollment hasn't completed
    #     (operator cancelled mid-flow).
    #   * ``sync_bearer_token_hash``: site → coord push credential.
    #   * ``coordinator_outbound_bearer_token``: coord → site push
    #     credential.  Leaving it intact would let the coordinator's
    #     own push worker keep firing at a removed site every tick.
    site.enrollment_token_hash = None
    site.sync_bearer_token_hash = None
    site.coordinator_outbound_bearer_token = None
    _log_audit(
        session,
        AUDIT_OP_SITE_REMOVED,
        actor_userid=actor_userid,
        target_site_id=site.id,
        details={"previous_status": previous_status},
    )
    return site


# ---------------------------------------------------------------------
# Site-side metadata refresh (called from rollup ingestion in 12.1.D)
# ---------------------------------------------------------------------


def record_sync(
    session: Session,
    site_id: Any,
    *,
    success: bool,
    host_count: Optional[int] = None,
    error: Optional[str] = None,
) -> FederationSite:
    """Mark that we just heard from a site.

    Called every time the coordinator processes a sync push from a
    site (or fails to).  Updates ``last_sync_at`` / ``last_sync_status``
    plus optionally the cached ``host_count``.  Does NOT log audit —
    sync events are too high-frequency to write per-row.
    """
    site = _ensure_site(session, site_id)
    site.last_sync_at = _utcnow_naive()
    site.last_sync_status = "success" if success else (error or "error")
    if host_count is not None and host_count >= 0:
        site.host_count = host_count
    return site
