"""
Tests for the air-gap deployment-invariant guard.

The policy lives in a pure function so it can be exhaustively tested without
any DB/config I/O.  Invariants (design openbao-deployment-and-airgap.md §5):
repository-role deployments must be single-tenant and must not federate.
"""

import pytest

from backend.startup.deployment_guards import (
    DeploymentInvariantError,
    check_deployment_invariants,
    enforce_deployment_invariants,
)


def test_standard_single_tenant_is_valid():
    assert check_deployment_invariants("standard", "none", False) == []


def test_standard_multitenant_is_valid():
    # Multi-tenancy is fine on a non-air-gapped (standard) deployment.
    assert check_deployment_invariants("standard", "none", True) == []


def test_collector_may_federate():
    # The internet-connected collector bridge may be a federation site.
    assert check_deployment_invariants("collector", "site", False) == []
    assert check_deployment_invariants("collector", "coordinator", False) == []


def test_repository_single_tenant_no_federation_is_valid():
    assert check_deployment_invariants("repository", "none", False) == []


def test_repository_with_multitenancy_violates():
    violations = check_deployment_invariants("repository", "none", True)
    assert len(violations) == 1
    assert "multitenancy" in violations[0].lower()


def test_repository_as_federation_site_violates():
    violations = check_deployment_invariants("repository", "site", False)
    assert len(violations) == 1
    assert "federation" in violations[0].lower()


def test_repository_as_federation_coordinator_violates():
    violations = check_deployment_invariants("repository", "coordinator", False)
    assert len(violations) == 1
    assert "federation" in violations[0].lower()


def test_repository_with_both_violations():
    violations = check_deployment_invariants("repository", "coordinator", True)
    assert len(violations) == 2


def test_enforce_raises_on_violation(monkeypatch):
    monkeypatch.setattr(
        "backend.services.server_config_service.get_server_role",
        lambda: "repository",
    )
    monkeypatch.setattr(
        "backend.services.server_config_service.get_federation_role",
        lambda: "site",
    )
    monkeypatch.setattr("backend.config.config.is_multitenancy_enabled", lambda: True)
    with pytest.raises(DeploymentInvariantError):
        enforce_deployment_invariants()


def test_enforce_passes_for_valid_deployment(monkeypatch):
    monkeypatch.setattr(
        "backend.services.server_config_service.get_server_role",
        lambda: "standard",
    )
    monkeypatch.setattr(
        "backend.services.server_config_service.get_federation_role",
        lambda: "none",
    )
    monkeypatch.setattr("backend.config.config.is_multitenancy_enabled", lambda: True)
    enforce_deployment_invariants()  # no raise


def test_enforce_is_best_effort_when_role_unresolvable(monkeypatch):
    def _boom():
        raise RuntimeError("DB not ready")

    monkeypatch.setattr("backend.services.server_config_service.get_server_role", _boom)
    # Should swallow and return rather than blocking boot.
    enforce_deployment_invariants()
