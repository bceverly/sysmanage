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
from backend.security import agent_identity, agent_reenroll
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)


def _refresh_existing_host(session, existing_host, registration_data) -> "models.Host":
    """Update an already-registered host's network/active fields from a
    re-registration payload.  Script-execution capability is intentionally
    NOT touched -- that's an admin-configured server-side setting."""
    try:
        existing_host.active = registration_data.active
        existing_host.ipv4 = registration_data.ipv4
        existing_host.ipv6 = registration_data.ipv6
        existing_host.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
        # Phase 19: refresh the capability advertisement on re-registration too.
        # An agent that gains or loses a capability (a package installed, an
        # OS upgrade) re-registers long before its next SYSTEM_INFO, and a
        # stale advertisement makes the dispatch gate refuse work the agent can
        # now do.  A payload without capabilities leaves the stored set alone.
        from backend.services.agent_capability_service import (
            apply_capability_report,
        )  # noqa: PLC0415

        apply_capability_report(
            existing_host, getattr(registration_data, "agent_capabilities", None)
        )
        session.commit()
        session.refresh(existing_host)
        return existing_host
    except Exception:
        session.rollback()
        raise


def existing_host_reply(
    existing_host, registration_nonce, reenroll_code=None, session=None
) -> dict:
    """The answer to a registration naming a host that already exists: no id
    or token (Phase 22.0) -- unless it is the registrant retrying with the
    nonce it created the host with (Phase 22; agent_identity), or a machine
    presenting the one-time code an administrator issued with "Allow
    re-enroll" (a rebuilt host; agent_reenroll), which gets a NEW token."""
    if session is not None and agent_reenroll.redeem(existing_host, reenroll_code):
        AuditService.log(
            db=session,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.HOST,
            entity_id=str(existing_host.id),
            entity_name=existing_host.fqdn,
            description=_(
                "Host '%(fqdn)s' re-enrolled with a one-time code; its old "
                "credential no longer works"
            )
            % {"fqdn": existing_host.fqdn},
            result=Result.SUCCESS,
            details={"reenrolled": True},
        )
        session.commit()
        session.refresh(existing_host)
        return registration_reply(existing_host, issue_credential=True)
    retry = agent_identity.registration_nonce_matches(existing_host, registration_nonce)
    if retry:
        logger.info(
            "Registration retry for %s with its nonce: re-sending its credential",
            sanitize_log(existing_host.fqdn),
        )
    if not retry and awaiting_reenroll(existing_host):
        # An administrator re-enrolled this host (no credential, pending): the
        # agent that lost its id gets it back, so it can claim the host and be
        # given a new token on first use.  Nothing it sends is accepted until
        # the host is approved again.
        logger.info(
            "Registration for re-enrolled host %s: sending its id",
            sanitize_log(existing_host.fqdn),
        )
        reply = registration_reply(existing_host, issue_credential=False)
        reply["id"] = str(existing_host.id)
        return reply
    return registration_reply(existing_host, issue_credential=retry)


def awaiting_reenroll(host) -> bool:
    """A host an administrator re-enrolled: its credential cleared and back to
    pending approval, waiting for its agent to claim it."""
    return (
        host.approval_status == "pending"
        and not host.host_token
        and not getattr(host, "requires_host_token", False)
    )


def _audit_registration_key_enrollment(session, host, validated_key) -> None:
    """Audit a host enrolled through a registration key (Phase 8.1)."""
    # Audit log: enrollment via registration key carries enough
    # context that the operator can correlate to the matched key.
    if validated_key is not None:
        AuditService.log(
            db=session,
            action_type=ActionType.CREATE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=_(
                "Host '%(fqdn)s' enrolled via registration key '%(key_name)s' (auto_approve=%(auto_approve)s)"
            )
            % {
                "fqdn": host.fqdn,
                "key_name": validated_key.name,
                "auto_approve": validated_key.auto_approve,
            },
            result=Result.SUCCESS,
            details={
                "registration_key_id": str(validated_key.id),
                "registration_key_name": validated_key.name,
                "access_group_id": (
                    str(validated_key.access_group_id)
                    if validated_key.access_group_id
                    else None
                ),
                "auto_approved": validated_key.auto_approve,
            },
        )


def registration_reply(host, issue_credential: bool) -> dict:
    """What a registration answers -- explicit, never the serialized row
    (which carried the token, the client certificate and every column).
    The id and token go only to the registration that created the host."""
    reply = {
        "result": True,
        "fqdn": host.fqdn,
        "approval_status": host.approval_status,
        "active": host.active,
    }
    if issue_credential:
        reply["id"] = str(host.id)
        reply["host_token"] = host.host_token
    return reply


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
    """Validate + consume a tenant enrollment token; return its placement.

    Returns a dict ``{"tenant_id", "site_id", "access_group_id"}`` on success
    (site / access-group ``None`` unless the token carries them -- Phase 18.1 S4),
    or ``None`` when multi-tenancy is DISABLED or no token was supplied -- a
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
        resolution = enrollment_service.validate_and_consume(session, raw_token)
    if resolution is None:
        raise HTTPException(
            status_code=403, detail=_("Invalid or expired enrollment token")
        )
    return resolution


def _apply_enrollment_token_placement(session, host, resolution):
    """Phase 18.1 S4: bind the host to the token's site / access group, if the
    consumed enrollment token carried them.  ``host.id`` must already be flushed;
    the caller commits.  Mirrors ``_apply_registration_key_enrollment``'s
    HostAccessGroup insert.  No-op for a token-less / placement-less token."""
    if not resolution:
        return
    site_id = resolution.get("site_id")
    if site_id:
        host.site_id = site_id
    access_group_id = resolution.get("access_group_id")
    if access_group_id:
        session.add(
            models.HostAccessGroup(
                host_id=host.id,
                access_group_id=access_group_id,
            )
        )


def tenant_host_refusal(db, message_data: dict):
    """Never make a no-tenant copy of a host that lives in a tenant.

    A SYSTEM_INFO that does not resolve to a tenant runs on the bootstrap
    database, where ``update_or_create_host`` creates the host by name when no
    row has it.  When that name already belongs to a tenant's host -- an agent
    that lost its host id, then registered into the tenant with its token --
    the new row is a pending phantom in "No tenant" that the agent then
    reports as, while the real host shows down.  Registration refuses the
    same case for a token-less agent (``_reject_if_fqdn_belongs_to_tenant``);
    this closes it on the first message.  An existing bootstrap row is left
    alone.  None when there is nothing to refuse."""
    from backend.config import config as _config  # noqa: PLC0415

    hostname = message_data.get("hostname")
    if not hostname or not _config.is_multitenancy_enabled():
        return None
    if db.query(models.Host.id).filter(models.Host.fqdn == hostname).first():
        return None
    from backend.websocket.inbound_processor import (  # noqa: PLC0415
        _find_host_in_tenant_dbs,
    )

    host, tenant_session = _find_host_in_tenant_dbs(None, hostname)
    if host is None:
        return None
    try:
        host_id = str(host.id)
    finally:
        tenant_session.close()
    logger.warning(
        "Refused a no-tenant host for %s: it belongs to a tenant (host %s); "
        "the agent must report as that host (re-enroll it if it lost its id)",
        sanitize_log(hostname),
        host_id,
    )
    return {
        "message_type": "error",
        "error_type": "host_belongs_to_tenant",
        "message": _(
            "This host belongs to a tenant, but the agent did not say which "
            "host it is. Re-enroll the host in its tenant, then restart the agent."
        ),
        "data": {},
    }


def _reject_if_fqdn_belongs_to_tenant(fqdn):
    """Close the phantom-duplicate loophole for a token-less registration.

    A registration with no enrollment token writes to the no-tenant/bootstrap
    database.  Dedup is per-partition (there is no cross-partition lookup), so if
    this ``fqdn`` already lives in a TENANT database, creating a server-scoped row
    here would be a cross-partition PHANTOM of a host that belongs to a tenant --
    exactly the ghost-row bug we chased.  Reject loudly (403) so the agent
    surfaces its missing/bad tenant binding and re-enrolls with its token instead
    of accreting a duplicate.  No-op when multi-tenancy is off (no tenant DBs to
    collide with) or the fqdn is genuinely new.
    """
    from backend.config import config as _config  # noqa: PLC0415

    if not _config.is_multitenancy_enabled():
        return

    from backend.websocket.inbound_processor import (
        _find_host_in_tenant_dbs,
    )  # noqa: PLC0415

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
        "tenant database -- a server-scoped row would be a phantom duplicate. The "
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
