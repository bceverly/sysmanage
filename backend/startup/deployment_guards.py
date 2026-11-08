# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Deployment-invariant guards.

Enforces the air-gap **appliance** invariants at startup (design:
``docs/planning/openbao-deployment-and-airgap.md`` §5):

  * An air-gapped (``repository``-role) deployment is **single-tenant** --
    multi-tenancy needs customer-owned external SSO, which can't reach an
    IdP offline, so ``multitenancy.enabled`` must be false there.
  * A ``repository``-role server does **not participate in federation**
    (neither ``coordinator`` nor ``site``) -- federation across the gap is
    impossible and within an enclave fights the segmentation that justifies
    the air gap.

The core check is a **pure function** (no I/O) so it is trivially testable;
the thin :func:`enforce_deployment_invariants` wrapper fetches the live
values (server/federation role from the DB singleton, multitenancy from
config) and fails fast.  This is the belt-and-suspenders runtime backstop to
the install-time config-builder gating.
"""

from typing import List

from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.startup.deployment_guards")

REPOSITORY_ROLE = "repository"
FEDERATION_PARTICIPANT_ROLES = ("coordinator", "site")


class DeploymentInvariantError(RuntimeError):
    """Raised when a deployment violates an air-gap appliance invariant."""


def check_deployment_invariants(
    server_role: str,
    federation_role: str,
    multitenancy_enabled: bool,
) -> List[str]:
    """Return a list of invariant-violation messages (empty == valid).

    Pure function -- no I/O, no config/DB access -- so the policy is unit
    testable in isolation.
    """
    violations: List[str] = []

    if server_role == REPOSITORY_ROLE and multitenancy_enabled:
        violations.append(
            "multitenancy.enabled is true on an air-gapped (repository-role) "
            "deployment. Multi-tenancy requires customer-owned external SSO, "
            "which is unreachable offline; air-gapped deployments must run "
            "single-tenant (multitenancy.enabled=false)."
        )

    if (
        server_role == REPOSITORY_ROLE
        and federation_role in FEDERATION_PARTICIPANT_ROLES
    ):
        violations.append(
            f"federation role '{federation_role}' is set on an air-gapped "
            "(repository-role) deployment. Air-gapped repository servers do not "
            "participate in federation -- deploy independent repository servers "
            "per network segment instead."
        )

    return violations


def unseal_key_warning(config_dict: dict) -> str:
    """The warning to log when the config carries OpenBAO unseal keys, else "".

    Pure function.  Nothing reads ``vault.server.unseal_keys`` -- OpenBAO is
    unsealed from its own root-only key file -- but the config is readable by
    the service and copied into backups, so a key left there opens OpenBAO for
    anyone holding a copy (ROADMAP 25.9).  Older source installs wrote it.
    """
    server = ((config_dict or {}).get("vault") or {}).get("server") or {}
    if not server.get("unseal_keys"):
        return ""
    return (
        "The SysManage config holds an OpenBAO unseal key "
        "(vault.server.unseal_keys). Anyone with a copy of the config, or of a "
        "backup of it, could unseal OpenBAO. Nothing reads the key there: "
        "OpenBAO is unsealed from /var/lib/openbao/init.json (packages) or "
        ".vault_credentials (source installs). To fix: 1) check that file "
        "holds the key; 2) delete the unseal_keys entry from the config; "
        "3) restart SysManage. On a source install, re-running "
        "scripts/sysmanage_secure_installation does steps 1 and 2 for you."
    )


def enforce_deployment_invariants() -> None:
    """Fetch live deployment state and abort startup on any violation.

    Reads the server/federation role from the DB singleton and the
    multitenancy flag from config.  Logs CRITICAL and raises
    :class:`DeploymentInvariantError` so a misconfigured appliance fails
    fast rather than silently running an unsupported combination.

    Best-effort by design: if the role can't be resolved yet (DB not ready),
    it logs and returns rather than blocking boot -- the install-time config
    builder is the primary gate; this is the runtime backstop.
    """
    try:
        from backend.config import config  # noqa: PLC0415
        from backend.services import server_config_service  # noqa: PLC0415

        server_role = server_config_service.get_server_role()
        federation_role = server_config_service.get_federation_role()
        multitenancy_enabled = config.is_multitenancy_enabled()
        warning = unseal_key_warning(config.get_config())
        if warning:
            logger.warning(warning)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not resolve deployment state for invariant check "
            "(continuing): %s",
            exc,
        )
        return

    violations = check_deployment_invariants(
        server_role, federation_role, multitenancy_enabled
    )
    if violations:
        for message in violations:
            logger.critical("Deployment invariant violation: %s", message)
        raise DeploymentInvariantError("; ".join(violations))
