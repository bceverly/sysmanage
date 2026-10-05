# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Agent identity: a host is its credential, not its name (Phase 22.0).

A hostname is public -- it is in DNS, certificates and inventories.  The
credential is the host_token: minted once, when the host is registered, and
kept by the agent.  Until 2026-10-01 the WebSocket handshake took a claimed
hostname on trust: a SYSTEM_INFO naming an approved host bound the session to
that host and answered with the host's token.  This module decides, from what
the agent proves, whether a SYSTEM_INFO may act as the host it names.

VERDICTS
--------
  new       no such host yet -- first contact creates it, as before.
  first_use the host exists but has never had a token (rows from before tokens
            existed): trust on first use, which mints one -- unchanged.
  verified  the agent presented the host's token.
  legacy    a pre-22.0 agent: it presents the host's id (and the matching
            name) but its stored token was overwritten by a registration
            response.  Accepted until the host is ratcheted (below).
  refused   anything else -- above all a bare name for a host that has a
            credential.  Nothing is bound and nothing is sent back.

THE RATCHET
-----------
An agent from 22.0 on keeps its token and advertises the capability
``persistent_host_token``.  The first time such an agent presents a valid
token, the host is marked ``requires_host_token`` and the legacy id-only
identity is refused for it from then on.  Hosts move to strict one by one as
their agents update, with no switch to flip; only an administrator's
re-enroll clears it.
"""

import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from backend.persistence.models import Host
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

PERSISTENT_TOKEN_CAPABILITY = "persistent_host_token"

NEW = "new"
FIRST_USE = "first_use"
VERIFIED = "verified"
LEGACY = "legacy"
REFUSED = "refused"

# Why a claim was refused -- also the error_type sent to the agent.
CREDENTIAL_REQUIRED = "host_credential_required"
CREDENTIAL_INVALID = "host_credential_invalid"


@dataclass
class Claim:
    """The outcome of checking a SYSTEM_INFO's identity."""

    verdict: str
    host: Optional[Host] = None
    reason: Optional[str] = None

    @property
    def accepted(self) -> bool:
        return self.verdict != REFUSED


def _host_by_id(db: Session, host_id) -> Optional[Host]:
    try:
        key = uuid.UUID(str(host_id))
    except (ValueError, TypeError):
        return None
    return db.query(Host).filter(Host.id == key).first()


def _token_matches(presented, stored) -> bool:
    return bool(presented and stored) and hmac.compare_digest(
        str(presented).encode(), str(stored).encode()
    )


def advertises_persistent_token(message_data: dict) -> bool:
    """True when the agent says it keeps its token (22.0 agents)."""
    report = message_data.get("agent_capabilities")
    if not isinstance(report, dict):
        return False
    capabilities = report.get("capabilities")
    return (
        isinstance(capabilities, list) and PERSISTENT_TOKEN_CAPABILITY in capabilities
    )


def check_claim(db: Session, message_data: dict) -> Claim:
    """Decide whether this SYSTEM_INFO may act as the host it names."""
    hostname = message_data.get("hostname")
    host_id = message_data.get("host_id")
    token = message_data.get("host_token")

    host = _host_by_id(db, host_id) if host_id else None
    if host is None and hostname:
        host = db.query(Host).filter(Host.fqdn == hostname).first()
    if host is None:
        return Claim(NEW)
    if not host.host_token:
        return Claim(FIRST_USE, host)
    if token:
        if _token_matches(token, host.host_token):
            return Claim(VERIFIED, host)
        return Claim(REFUSED, host, CREDENTIAL_INVALID)
    if (
        host_id
        and str(host.id) == str(host_id)
        and host.fqdn == hostname
        and not host.requires_host_token
    ):
        return Claim(LEGACY, host)
    return Claim(REFUSED, host, CREDENTIAL_REQUIRED)


def apply_ratchet(claim: Claim, message_data: dict) -> bool:
    """Mark the host token-required once a 22.0 agent proves its token.
    Returns True when it changed (the caller commits)."""
    host = claim.host
    if (
        claim.verdict == VERIFIED
        and host is not None
        and not host.requires_host_token
        and advertises_persistent_token(message_data)
    ):
        host.requires_host_token = True
        logger.info(
            "Host %s now requires its token (agent keeps its credential)",
            sanitize_log(host.fqdn),
        )
        return True
    return False


# -- idempotent registration (Phase 22) -----------------------------------------
# The id and token go only to the registration that created the host -- or so
# it was: when that reply was lost (a timeout on a slow link, a server restart
# at the wrong moment) the agent's retry found "an existing host", got no
# credential, and every session after was refused host_credential_required
# with no way back but an admin re-enroll (6 of 10,000 simulated agents on a
# slow Wi-Fi fleet, 2026-10-05).  An agent now sends a random nonce with every
# registration attempt; the server keeps its hash on the host it creates, and
# a retry presenting the same nonce gets the same id and token.  Only the
# registrant knows the nonce, so naming a host still yields nothing; and the
# hash is cleared the first time the agent proves its token, so a nonce can
# recover a credential that was never received, never one in use.
REGISTRATION_NONCE_MIN_LENGTH = 32


def registration_nonce_hash(nonce) -> Optional[str]:
    """SHA-256 (hex) of a usable nonce, or None (absent or too short)."""
    if not isinstance(nonce, str) or len(nonce) < REGISTRATION_NONCE_MIN_LENGTH:
        return None
    return hashlib.sha256(nonce.encode("utf-8")).hexdigest()


def registration_nonce_matches(host: Host, nonce) -> bool:
    """True when ``nonce`` is the one ``host`` was created with, and the host's
    agent has not yet proven its token."""
    presented = registration_nonce_hash(nonce)
    stored = getattr(host, "registration_nonce_hash", None)
    return bool(presented and stored) and hmac.compare_digest(presented, stored)


def forget_registration_nonce(claim: Claim) -> bool:
    """Clear the nonce once the agent proves its token.  True when it changed
    (the caller commits)."""
    host = claim.host
    if claim.verdict == VERIFIED and host is not None and host.registration_nonce_hash:
        host.registration_nonce_hash = None
        return True
    return False


def log_refusal(claim: Claim, message_data: dict, source: Optional[str]) -> None:
    """Loud, with the context an operator needs to tell a reinstalled host
    (needs a re-enroll) from someone claiming a host they are not."""
    logger.warning(
        "Refused agent session claiming host %s (id %s) from %s: %s "
        "(host_id presented: %s, token presented: %s)",
        sanitize_log(message_data.get("hostname")),
        sanitize_log(claim.host.id if claim.host else None),
        sanitize_log(source),
        sanitize_log(claim.reason),
        bool(message_data.get("host_id")),
        bool(message_data.get("host_token")),
    )


def verified_host_id(host_id, token) -> Optional[str]:
    """The host id, if ``token`` is that host's credential; else None.

    For callers without a session -- the connection limit on ``/agent/auth``
    keys a verified agent on its host instead of its address (Phase 22.2).
    The host's row is read from the database that owns it (its tenant's,
    under multi-tenancy).  Never raises: any failure is "not verified"."""
    if not host_id or not token:
        return None
    try:
        host_uuid = uuid.UUID(str(host_id))
        from sqlalchemy.orm import (
            sessionmaker,
        )  # pylint: disable=import-outside-toplevel

        from backend.persistence.db import (
            get_engine,
        )  # pylint: disable=import-outside-toplevel
        from backend.persistence.partitions import (  # pylint: disable=import-outside-toplevel
            tenant_engine_for_host,
        )

        engine = tenant_engine_for_host(str(host_uuid)) or get_engine()
        with sessionmaker(bind=engine)() as session:
            stored = (
                session.query(Host.host_token).filter(Host.id == host_uuid).scalar()
            )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug(
            "Could not verify the identity presented for %s", sanitize_log(host_id)
        )
        return None
    return str(host_uuid) if _token_matches(token, stored) else None
