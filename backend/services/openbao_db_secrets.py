"""
OpenBAO database-secrets credential broker — Phase 13.1.C.

Leases *dynamic, short-lived, per-tenant database credentials* from
OpenBAO's database secrets engine on demand (design §8).  No tenant DB
password is ever stored: OpenBAO creates a real DB user with a TTL, returns
it once, and auto-revokes it when the lease expires.  Revocation is
centralized; a leaked lease auto-expires.

This module is a thin client over the OpenBAO HTTP API (reusing
``VaultService``'s authenticated session).  The caching + per-tenant warm
pools that keep this off the request hot path live in
``backend/persistence/tenant_engine.py``.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from backend.config import config

logger = logging.getLogger(__name__)


@dataclass
class DbLease:
    """A leased dynamic DB credential from OpenBAO."""

    username: str
    password: str
    lease_id: Optional[str]
    lease_duration: int  # seconds the credential is valid


class DbSecretsError(RuntimeError):
    """Raised when a dynamic DB credential cannot be leased/renewed/revoked."""


def lease_credentials(role: str) -> DbLease:
    """Lease dynamic DB credentials for ``role`` from OpenBAO.

    ``role`` is the OpenBAO database-secrets role (``registry_tenant_placement
    .openbao_role``) configured to issue users on the tenant's database.
    Raises :class:`DbSecretsError` on any failure.
    """
    # Late import keeps this module importable without the vault deps.
    from backend.services.vault_service import VaultService  # noqa: PLC0415

    mount = config.get_vault_database_mount_path()
    path = f"{mount}/creds/{role}"
    try:
        svc = VaultService()
        # OpenBAO returns the dynamic cred under data.{username,password} and
        # the lease metadata at the top level (lease_id, lease_duration).
        response = svc.make_raw_request("GET", path)
    except Exception as exc:  # noqa: BLE001
        raise DbSecretsError(
            f"Failed to lease DB credentials for role {role!r}: {exc}"
        ) from exc

    data = (response or {}).get("data") or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        raise DbSecretsError(f"OpenBAO returned no username/password for role {role!r}")
    return DbLease(
        username=username,
        password=password,
        lease_id=(response or {}).get("lease_id"),
        lease_duration=int((response or {}).get("lease_duration") or 3600),
    )


def renew_lease(lease_id: str, increment: Optional[int] = None) -> int:
    """Renew a lease; returns the new lease_duration (seconds).  Best-effort.

    Returns 0 if renewal isn't possible (caller should then re-lease).
    """
    if not lease_id:
        return 0
    from backend.services.vault_service import VaultService  # noqa: PLC0415

    payload = {"lease_id": lease_id}
    if increment:
        payload["increment"] = increment
    try:
        response = VaultService().make_raw_request("PUT", "sys/leases/renew", payload)
        return int((response or {}).get("lease_duration") or 0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Lease renew failed for %s: %s", lease_id, exc)
        return 0


def revoke_lease(lease_id: str) -> bool:
    """Revoke a lease (best-effort).  Returns True on success."""
    if not lease_id:
        return False
    from backend.services.vault_service import VaultService  # noqa: PLC0415

    try:
        VaultService().make_raw_request(
            "PUT", "sys/leases/revoke", {"lease_id": lease_id}
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Lease revoke failed for %s: %s", lease_id, exc)
        return False
