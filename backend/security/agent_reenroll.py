# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Re-enroll with a one-time code: a rebuilt host takes over its record
(2026-11-24, ROADMAP 27.2).

Since Phase 22.0 a host is its token, never its name, and an agent that lost
its database is refused ``host_credential_required``.  The administrator's
"Re-enroll Agent" (``host_approval.reenroll_host``) answers that by hand: it
clears the credential and puts the host back to pending, the next agent to
claim it gets a token, and someone approves it again.

A rebuild or migration needs the same without a person in the loop, and
without the race where whichever machine claims the host first gets it.
So the job issues a one-time code (``issue``) and hands it to the new
machine (``security.reenroll_code`` in its agent config, written by the
first-boot step); an agent registering under the host's name with that code
takes over the existing record:

* a NEW token is minted and sent to it; the old one stops working at once;
* the host's agent certificate is cleared, so an old one is refused and the
  new agent gets its own (25.10);
* the code is spent, and it expires unused after ``CODE_TTL``.

Only the code's SHA-256 is stored.  Naming a host still yields nothing: the
code is what proves SysManage meant it.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from backend.persistence import models
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def issue(host: models.Host, issued_by: str) -> Tuple[str, datetime]:
    """A new one-time code for ``host`` (replacing any earlier one) and when
    it expires.  The caller audits and commits; the code is never stored."""
    code = secrets.token_urlsafe(32)
    expires = _now() + CODE_TTL
    host.reenroll_code_hash = _hash(code)
    host.reenroll_code_expires_at = expires
    host.reenroll_code_by = issued_by
    return code, expires


def cancel(host: models.Host) -> bool:
    """Withdraw an unused code; True when there was one."""
    had = bool(host.reenroll_code_hash)
    host.reenroll_code_hash = None
    host.reenroll_code_expires_at = None
    host.reenroll_code_by = None
    return had


def pending_until(host: models.Host) -> Optional[datetime]:
    """When ``host``'s unused code expires, or None (no code, or expired)."""
    expires = getattr(host, "reenroll_code_expires_at", None)
    if not getattr(host, "reenroll_code_hash", None) or expires is None:
        return None
    return expires if expires > _now() else None


def redeem(host: models.Host, code) -> bool:
    """Take over ``host`` with ``code``: True (and the host re-keyed) when
    the code is this host's, unexpired and unspent.  The caller audits and
    commits."""
    if not isinstance(code, str) or not code or pending_until(host) is None:
        return False
    if not hmac.compare_digest(_hash(code), host.reenroll_code_hash):
        logger.warning(
            "A re-enroll code that is not this host's was presented for %s",
            sanitize_log(host.fqdn),
        )
        return False
    cancel(host)
    host.host_token = models.generate_secure_host_token()
    # The nonce belonged to the old agent's first registration.
    host.registration_nonce_hash = None
    for column in (
        "client_certificate",
        "certificate_serial",
        "certificate_issued_at",
        "certificate_expires_at",
        "certificate_last_presented_at",
        "previous_certificate_serial",
    ):
        setattr(host, column, None)
    logger.info("Host %s re-enrolled with a new credential", sanitize_log(host.fqdn))
    return True
