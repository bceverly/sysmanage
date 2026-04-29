"""
Tests for the Phase 8.3 package-compliance evaluator + API.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from types import SimpleNamespace

import pytest

from backend.persistence.models.package_compliance import (
    CONSTRAINT_BLOCKED,
    CONSTRAINT_REQUIRED,
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
)
from backend.services.package_compliance import evaluate_host_against_profile

# ----------------------------------------------------------------------
# Evaluator unit tests (pure-Python, no DB)
# ----------------------------------------------------------------------


def _c(**kw):
    """Build a duck-typed constraint with sensible defaults."""
    defaults = dict(
        id="00000000-0000-0000-0000-000000000001",
        package_name="curl",
        package_manager=None,
        constraint_type=CONSTRAINT_REQUIRED,
        version_op=None,
        version=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestEvaluatorRequired:
    def test_compliant_when_required_pkg_installed(self):
        installed = [{"name": "curl", "version": "7.68.0"}]
        constraints = [_c(constraint_type=CONSTRAINT_REQUIRED)]
        status, violations = evaluate_host_against_profile(installed, constraints)
        assert status == STATUS_COMPLIANT
        assert violations == []

    def test_non_compliant_when_required_pkg_missing(self):
        installed = [{"name": "wget", "version": "1.21.0"}]
        constraints = [_c(constraint_type=CONSTRAINT_REQUIRED)]
        status, violations = evaluate_host_against_profile(installed, constraints)
        assert status == STATUS_NON_COMPLIANT
        assert violations[0]["package_name"] == "curl"
        assert violations[0]["reason"] == "package not installed"

    def test_required_with_version_constraint_met(self):
        installed = [{"name": "curl", "version": "7.68.0"}]
        constraints = [
            _c(
                constraint_type=CONSTRAINT_REQUIRED,
                version_op=">=",
                version="7.0.0",
            )
        ]
        status, _violations = evaluate_host_against_profile(installed, constraints)
        assert status == STATUS_COMPLIANT

    def test_required_with_version_constraint_unmet(self):
        installed = [{"name": "curl", "version": "6.0.0"}]
        constraints = [
            _c(
                constraint_type=CONSTRAINT_REQUIRED,
                version_op=">=",
                version="7.0.0",
            )
        ]
        status, violations = evaluate_host_against_profile(installed, constraints)
        assert status == STATUS_NON_COMPLIANT
        assert "satisfies" in violations[0]["reason"]


class TestEvaluatorBlocked:
    def test_compliant_when_blocked_pkg_absent(self):
        installed = [{"name": "curl", "version": "7.68.0"}]
        constraints = [_c(package_name="telnet", constraint_type=CONSTRAINT_BLOCKED)]
        status, violations = evaluate_host_against_profile(installed, constraints)
        assert status == STATUS_COMPLIANT
        assert violations == []

    def test_non_compliant_when_blocked_pkg_present(self):
        installed = [{"name": "telnet", "version": "0.17"}]
        constraints = [_c(package_name="telnet", constraint_type=CONSTRAINT_BLOCKED)]
        status, violations = evaluate_host_against_profile(installed, constraints)
        assert status == STATUS_NON_COMPLIANT
        assert violations[0]["constraint_type"] == CONSTRAINT_BLOCKED
        assert "blocked" in violations[0]["reason"]

    def test_blocked_with_version_op_only_fires_on_match(self):
        """BLOCKED with version op:  fires only on installed versions
        that SATISFY the op.  Newer-than-X is blocked → an installed
        OLDER-than-X passes."""
        installed = [{"name": "openssl", "version": "1.0.0"}]
        constraints = [
            _c(
                package_name="openssl",
                constraint_type=CONSTRAINT_BLOCKED,
                version_op=">=",
                version="3.0.0",
            )
        ]
        status, violations = evaluate_host_against_profile(installed, constraints)
        assert status == STATUS_COMPLIANT
        assert violations == []

        # Now an actually-blocked version:
        installed_bad = [{"name": "openssl", "version": "3.1.0"}]
        status_bad, violations_bad = evaluate_host_against_profile(
            installed_bad, constraints
        )
        assert status_bad == STATUS_NON_COMPLIANT
        assert "3.1.0" in violations_bad[0]["reason"]


class TestEvaluatorMixedRules:
    def test_multiple_constraints_aggregate_violations(self):
        installed = [
            {"name": "curl", "version": "6.0.0"},  # too old (REQUIRED >= 7)
            {"name": "telnet", "version": "0.17"},  # BLOCKED, present
        ]
        constraints = [
            _c(
                package_name="curl",
                constraint_type=CONSTRAINT_REQUIRED,
                version_op=">=",
                version="7.0.0",
            ),
            _c(
                id="00000000-0000-0000-0000-000000000002",
                package_name="telnet",
                constraint_type=CONSTRAINT_BLOCKED,
            ),
        ]
        status, violations = evaluate_host_against_profile(installed, constraints)
        assert status == STATUS_NON_COMPLIANT
        assert len(violations) == 2

    def test_package_manager_filter_narrows_match(self):
        installed = [
            {"name": "curl", "version": "1.0.0", "manager": "apt"},
            {"name": "curl", "version": "2.0.0", "manager": "snap"},
        ]
        constraints = [
            _c(
                package_name="curl",
                package_manager="snap",
                constraint_type=CONSTRAINT_REQUIRED,
                version_op="==",
                version="2.0.0",
            )
        ]
        status, _violations = evaluate_host_against_profile(installed, constraints)
        # The snap version matches; the apt version is ignored.
        assert status == STATUS_COMPLIANT


# ----------------------------------------------------------------------
# API tests
# ----------------------------------------------------------------------


class TestPackageProfileAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/api/package-profiles")
        assert r.status_code in [401, 403]


class TestPackageProfileCrud:
    def test_create_with_constraints(self, client, auth_headers):
        r = client.post(
            "/api/package-profiles",
            json={
                "name": "prod-required",
                "constraints": [
                    {"package_name": "curl", "constraint_type": "REQUIRED"},
                    {"package_name": "telnet", "constraint_type": "BLOCKED"},
                ],
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "prod-required"
        assert len(body["constraints"]) == 2

    def test_create_with_invalid_constraint_type(self, client, auth_headers):
        r = client.post(
            "/api/package-profiles",
            json={
                "name": "bogus",
                "constraints": [{"package_name": "x", "constraint_type": "OPTIONAL"}],
            },
            headers=auth_headers,
        )
        # 422 = Pydantic field-validator rejection
        assert r.status_code == 422

    def test_create_with_invalid_version_op(self, client, auth_headers):
        r = client.post(
            "/api/package-profiles",
            json={
                "name": "bogus-op",
                "constraints": [
                    {
                        "package_name": "x",
                        "constraint_type": "REQUIRED",
                        "version_op": "lol",
                        "version": "1.0",
                    }
                ],
            },
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_get_one_with_constraints(self, client, auth_headers):
        created = client.post(
            "/api/package-profiles",
            json={
                "name": "fetch-me",
                "constraints": [
                    {"package_name": "wget", "constraint_type": "REQUIRED"}
                ],
            },
            headers=auth_headers,
        ).json()
        r = client.get(f"/api/package-profiles/{created['id']}", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["constraints"]) == 1

    def test_update_replaces_constraints(self, client, auth_headers):
        created = client.post(
            "/api/package-profiles",
            json={
                "name": "to-rewrite",
                "constraints": [{"package_name": "old", "constraint_type": "REQUIRED"}],
            },
            headers=auth_headers,
        ).json()
        r = client.put(
            f"/api/package-profiles/{created['id']}",
            json={
                "constraints": [{"package_name": "new", "constraint_type": "REQUIRED"}]
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        names = [c["package_name"] for c in r.json()["constraints"]]
        assert names == ["new"]  # exactly the new list, not appended

    def test_delete(self, client, auth_headers):
        created = client.post(
            "/api/package-profiles",
            json={"name": "ephemeral"},
            headers=auth_headers,
        ).json()
        r = client.delete(
            f"/api/package-profiles/{created['id']}", headers=auth_headers
        )
        assert r.status_code == 200
