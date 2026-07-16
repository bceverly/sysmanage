# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the air-gap compliance context (Phase 11.3)."""

# pylint: disable=missing-class-docstring,missing-function-docstring


from backend.services.airgap_compliance_context import classify_compliance_gap


class TestClassifyComplianceGap:
    def test_empty_host_packages_returns_empty_buckets(self):
        out = classify_compliance_gap([], {}, {})
        assert out == {"not_applied": [], "not_transferred": [], "current": []}

    def test_package_with_newer_available_locally_is_not_applied(self):
        host = [{"name": "openssl", "version": "3.0.0"}]
        manifest = {
            "files": [
                {
                    "path": "openssl-3.0.5-1.deb",
                    "sha256": "x",
                    "size": 1,
                    "role": "package",
                    "metadata": {
                        "package_name": "openssl",
                        "package_version": "3.0.5",
                    },
                }
            ],
        }
        out = classify_compliance_gap(host, manifest, {})
        assert len(out["not_applied"]) == 1
        assert out["not_applied"][0]["package"] == "openssl"
        assert out["not_applied"][0]["installed"] == "3.0.0"
        assert out["not_applied"][0]["available"] == "3.0.5"

    def test_cve_present_but_fix_not_in_mirror_is_not_transferred(self):
        host = [{"name": "log4j", "version": "2.14.0"}]
        manifest = {"files": []}  # log4j not on local mirror at all
        cve_snapshot = {
            "cves": [
                {
                    "package_name": "log4j",
                    "cve_id": "CVE-2021-44228",
                    "fix_version": "2.17.1",
                }
            ],
        }
        out = classify_compliance_gap(host, manifest, cve_snapshot)
        assert len(out["not_transferred"]) == 1
        assert out["not_transferred"][0]["cve_id"] == "CVE-2021-44228"
        assert out["not_transferred"][0]["fix_version"] == "2.17.1"

    def test_package_at_latest_version_is_current(self):
        host = [{"name": "curl", "version": "8.5.0"}]
        manifest = {
            "files": [
                {
                    "path": "curl-8.5.0.deb",
                    "sha256": "x",
                    "size": 1,
                    "role": "package",
                    "metadata": {
                        "package_name": "curl",
                        "package_version": "8.5.0",
                    },
                }
            ],
        }
        out = classify_compliance_gap(host, manifest, {})
        assert len(out["current"]) == 1
        assert out["current"][0]["package"] == "curl"


class TestClassifyComplianceGapPriority:
    """When a package is BOTH out-of-date AND has a CVE only in public
    snapshot, ``not_applied`` wins — fixing locally is the cheaper path."""

    def test_not_applied_takes_precedence_over_not_transferred(self):
        host = [{"name": "nginx", "version": "1.18.0"}]
        manifest = {
            "files": [
                {
                    "path": "nginx-1.20.0.deb",
                    "sha256": "x",
                    "size": 1,
                    "role": "package",
                    "metadata": {
                        "package_name": "nginx",
                        "package_version": "1.20.0",
                    },
                }
            ],
        }
        cve_snapshot = {
            "cves": [
                {
                    "package_name": "nginx",
                    "cve_id": "CVE-X",
                    "fix_version": "1.25.0",
                }
            ],
        }
        out = classify_compliance_gap(host, manifest, cve_snapshot)
        assert len(out["not_applied"]) == 1
        assert len(out["not_transferred"]) == 0
