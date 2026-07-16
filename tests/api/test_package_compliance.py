# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 8.3 package-compliance evaluator + Phase 11.5
license-gated API.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
#
# Phase 11.5 gates every route on ``compliance_engine`` being loaded.
# These tests don't exercise the real Cython .so — they verify route
# behaviour, so we hand the route a MagicMock whose ``evaluate_host_status``
# delegates to the OSS evaluator (the engine version is itself a port
# of the OSS logic).  The Pro+ engine's own tests cover the Cython
# implementation under
# ``module-source/compliance_engine/test_compliance_engine_package_profiles.py``.


def _oss_evaluate_host_status(profile_dict, installed):
    """OSS-side mirror of compliance_engine.evaluate_host_status.

    The route hands the engine a profile dict containing already-
    serialized constraint dicts; rewrap them as duck-typed rows so the
    OSS evaluator (which reads attributes) can consume them.
    """
    constraints = [SimpleNamespace(**c) for c in profile_dict["constraints"]]
    return evaluate_host_against_profile(installed, constraints)


@pytest.fixture
def _engine_loaded():
    """Patch ``module_loader.get_module`` so ``_check_compliance_module``
    finds an engine surface."""
    mock_engine = MagicMock()
    mock_engine.evaluate_host_status = _oss_evaluate_host_status
    with patch(
        "backend.api.package_compliance.module_loader.get_module",
        return_value=mock_engine,
    ):
        yield mock_engine


class TestPackageProfileProplusGate:
    """When ``compliance_engine`` isn't loaded, every route returns 402."""

    @pytest.fixture
    def _engine_absent(self):
        with patch(
            "backend.api.package_compliance.module_loader.get_module",
            return_value=None,
        ):
            yield

    def test_list_returns_402(self, client, auth_headers, _engine_absent):
        r = client.get("/api/v1/package-profiles", headers=auth_headers)
        assert r.status_code == 402

    def test_create_returns_402(self, client, auth_headers, _engine_absent):
        r = client.post(
            "/api/v1/package-profiles",
            json={"name": "x"},
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_get_returns_402(self, client, auth_headers, _engine_absent):
        r = client.get(
            "/api/v1/package-profiles/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_update_returns_402(self, client, auth_headers, _engine_absent):
        r = client.put(
            "/api/v1/package-profiles/00000000-0000-0000-0000-000000000000",
            json={},
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_delete_returns_402(self, client, auth_headers, _engine_absent):
        r = client.delete(
            "/api/v1/package-profiles/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_scan_returns_402(self, client, auth_headers, _engine_absent):
        r = client.post(
            "/api/v1/package-profiles/"
            "00000000-0000-0000-0000-000000000000/scan/"
            "00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_dispatch_returns_402(self, client, auth_headers, _engine_absent):
        r = client.post(
            "/api/v1/package-profiles/"
            "00000000-0000-0000-0000-000000000000/dispatch/"
            "00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_status_for_host_returns_402(self, client, auth_headers, _engine_absent):
        r = client.get(
            "/api/v1/package-profiles/status/host/"
            "00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert r.status_code == 402


class TestPackageProfileAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/api/v1/package-profiles")
        assert r.status_code in [401, 403]


class TestPackageProfileCrud:
    @pytest.fixture(autouse=True)
    def _gate(self, _engine_loaded):
        yield

    def test_create_with_constraints(self, client, auth_headers):
        r = client.post(
            "/api/v1/package-profiles",
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
            "/api/v1/package-profiles",
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
            "/api/v1/package-profiles",
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
            "/api/v1/package-profiles",
            json={
                "name": "fetch-me",
                "constraints": [
                    {"package_name": "wget", "constraint_type": "REQUIRED"}
                ],
            },
            headers=auth_headers,
        ).json()
        r = client.get(
            f"/api/v1/package-profiles/{created['id']}", headers=auth_headers
        )
        assert r.status_code == 200
        assert len(r.json()["constraints"]) == 1

    def test_update_replaces_constraints(self, client, auth_headers):
        created = client.post(
            "/api/v1/package-profiles",
            json={
                "name": "to-rewrite",
                "constraints": [{"package_name": "old", "constraint_type": "REQUIRED"}],
            },
            headers=auth_headers,
        ).json()
        r = client.put(
            f"/api/v1/package-profiles/{created['id']}",
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
            "/api/v1/package-profiles",
            json={"name": "ephemeral"},
            headers=auth_headers,
        ).json()
        r = client.delete(
            f"/api/v1/package-profiles/{created['id']}", headers=auth_headers
        )
        assert r.status_code == 200
