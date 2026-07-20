# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Private registration sync-helpers for the host-registration flow.

These helpers were extracted from ``backend.api.host`` to keep that module's
size under the line-count cap.  They are re-imported back into ``host`` so the
public API (including ``host._resolve_enrollment_tenant`` /
``host._reject_if_fqdn_belongs_to_tenant`` used by tests) is unchanged.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from backend.i18n import _
from backend.persistence import db, models
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)


def _refresh_existing_host(session, existing_host, registration_data) -> "models.Host":
    """Update an already-registered host's network/active fields from a
    re-registration payload.  Script-execution capability is intentionally
    NOT touched — that's an admin-configured server-side setting."""
    print("Updating existing host with minimal registration data...")
    try:
        existing_host.active = registration_data.active
        existing_host.ipv4 = registration_data.ipv4
        existing_host.ipv6 = registration_data.ipv6
        existing_host.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
        print(
            f"Before commit - FQDN: {existing_host.fqdn}, Active: {existing_host.active}"
        )
        session.commit()
        print("Database commit successful")
        session.refresh(existing_host)
        print("After refresh - Host updated with minimal data")
        return existing_host
    except Exception as e:
        print(f"Error updating existing host: {e}")
        session.rollback()
        raise


def _validate_registration_key(session, raw_key):
    """Resolve a registration key string to a usable ``RegistrationKey``
    row.  Returns the row when valid, ``None`` when no key was supplied,
    raises 403 otherwise.  We deliberately don't leak which condition
    (revoked/expired/max-uses) failed."""
    if not raw_key:
        return None
    validated_key = (
        session.query(models.RegistrationKey)
        .filter(models.RegistrationKey.key == raw_key)
        .first()
    )
    if validated_key is None or not validated_key.is_usable():
        raise HTTPException(
            status_code=403,
            detail=_("Invalid or expired registration key"),
        )
    return validated_key


def _resolve_enrollment_tenant(raw_token):
    """Validate + consume a tenant enrollment token; return its tenant id.

    Returns ``None`` when multi-tenancy is DISABLED or no token was supplied — a
    token-less registration is still a legitimate server-scoped ("No tenant")
    host while that concept exists.  Raises 403 for a supplied-but-invalid token
    (unknown / revoked / expired / out of uses).  Consumes one use on success
    (bumps use_count / last_used_at).

    A MISSING token is NOT rejected here: the phantom-duplicate loophole is
    closed narrowly in ``register_host`` via ``_reject_if_fqdn_belongs_to_tenant``
    (which only fails a token-less registration when the fqdn already lives in a
    tenant DB), so ordinary server-scoped registration keeps working.
    """
    from backend.config import config as _config  # noqa: PLC0415

    if not raw_token:
        return None

    if not _config.is_multitenancy_enabled():
        return None

    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )
    from backend.services import enrollment_service  # noqa: PLC0415

    with partition_session(partition=PARTITION_REGISTRY) as session:
        tenant_id = enrollment_service.validate_and_consume(session, raw_token)
    if tenant_id is None:
        raise HTTPException(
            status_code=403, detail=_("Invalid or expired enrollment token")
        )
    return tenant_id


def _reject_if_fqdn_belongs_to_tenant(fqdn):
    """Close the phantom-duplicate loophole for a token-less registration.

    A registration with no enrollment token writes to the no-tenant/bootstrap
    database.  Dedup is per-partition (there is no cross-partition lookup), so if
    this ``fqdn`` already lives in a TENANT database, creating a server-scoped row
    here would be a cross-partition PHANTOM of a host that belongs to a tenant —
    exactly the ghost-row bug we chased.  Reject loudly (403) so the agent
    surfaces its missing/bad tenant binding and re-enrolls with its token instead
    of accreting a duplicate.  No-op when multi-tenancy is off (no tenant DBs to
    collide with) or the fqdn is genuinely new.
    """
    from backend.config import config as _config  # noqa: PLC0415

    if not _config.is_multitenancy_enabled():
        return

    from backend.websocket.inbound_processor import (  # noqa: PLC0415
        _find_host_in_tenant_dbs,
    )

    host, tenant_session = _find_host_in_tenant_dbs(None, fqdn)
    if host is None:
        return
    try:
        owner_fqdn = host.fqdn
    finally:
        tenant_session.close()

    # False positive: the only logged value is a sanitized FQDN (a hostname);
    # the word "token" appears solely in the static advice text, not as a
    # secret. See sanitize_log() and owner_fqdn = host.fqdn above.
    logger.warning(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        "Rejected token-less registration for fqdn=%s: it already belongs to a "
        "tenant database — a server-scoped row would be a phantom duplicate. The "
        "agent must re-register with its enrollment token.",
        sanitize_log(owner_fqdn),
    )
    raise HTTPException(
        status_code=403,
        detail=_(
            "This host already belongs to a tenant. Re-register with its "
            "enrollment token instead of registering server-scoped."
        ),
    )


def _host_write_engine(enrollment_tenant_id):
    """The engine the new host row (and its tenant-scoped enrollment side-effects)
    is created on: the enrolling tenant's database when a token resolved a tenant,
    otherwise the bootstrap engine.  Extracted from ``register_host`` to keep its
    cognitive complexity under the cap."""
    if enrollment_tenant_id is None:
        return db.get_engine()
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_TENANT,
        resolve_engine,
    )

    return resolve_engine(partition=PARTITION_TENANT, tenant_id=enrollment_tenant_id)


def _apply_registration_key_enrollment(session, host, validated_key):
    """Phase 8.1: enroll the host into the matched key's access group and bump the
    key's ``use_count`` / ``last_used_at``.  No-op when no key matched.  Extracted
    from ``register_host`` to keep its cognitive complexity under the cap; the
    caller commits so "use_count reflects successful enrollments" stays atomic."""
    if validated_key is None:
        return
    if validated_key.access_group_id is not None:
        session.add(
            models.HostAccessGroup(
                host_id=host.id,
                access_group_id=validated_key.access_group_id,
            )
        )
    validated_key.use_count = (validated_key.use_count or 0) + 1
    validated_key.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
