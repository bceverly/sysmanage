# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for Phase 20.1 config-management prerequisite evaluation."""

import pytest

from backend.services import config_mgmt_prereq as prereq


def host(platform, release=""):
    return {"platform": platform, "platform_release": release}


def pkg(name, version):
    return {"package_name": name, "package_version": version}


class TestVersionComparison:
    """Version compare is where the silent bug lives."""

    def test_lexical_comparison_would_be_wrong_and_is_not_used(self):
        # "2.9" > "2.20" as STRINGS.  A host on 2.9 must not satisfy a 2.20
        # floor just because its version sorts higher alphabetically.
        installed, floor = "2.9", "2.20"
        assert installed > floor, "the naive string compare really is backwards"
        assert prereq.meets_minimum(installed, floor) is False

    @pytest.mark.parametrize(
        "installed,minimum,expected",
        [
            ("2.20", "2.20", True),
            ("2.20.1", "2.20", True),
            ("2.21.3", "2.20", True),
            ("3.0", "2.20", True),
            ("2.19.9", "2.20", False),
            ("2.18.16", "2.20", False),
            ("1.9", "2.20", False),
        ],
    )
    def test_numeric_ordering(self, installed, minimum, expected):
        assert prereq.meets_minimum(installed, minimum) is expected

    @pytest.mark.parametrize("version", ["", None, "unknown", "not-a-version"])
    def test_unparseable_versions_fail_closed(self, version):
        # Better to ask an operator to look than to treat an unknown as good.
        assert prereq.meets_minimum(version, "2.20") is False

    def test_real_measured_versions_all_clear_the_floor(self):
        # Every version the spike found on a real box, 2026-08-26.
        for measured in ("2.20.1", "2.21.1", "2.20.4", "2.21.0", "2.21.3"):
            assert prereq.meets_minimum(measured, "2.20") is True

    def test_freebsd_style_port_revision_suffix_parses(self):
        assert prereq.meets_minimum("2.21.1_1", "2.20") is True


class TestPackageMatching:
    def test_literal_names_match_themselves(self):
        found = prereq.find_installed([pkg("ansible-core", "2.20.4")], "ansible-core")
        assert found["package_version"] == "2.20.4"

    def test_freebsd_glob_matches_whatever_python_prefix_is_current(self):
        # The whole reason the pattern exists: py312 today, py313 tomorrow.
        for name in ("py311-ansible-core", "py312-ansible-core", "py313-ansible-core"):
            assert prereq.find_installed([pkg(name, "2.21.1")], "py3*-ansible-core")

    def test_glob_does_not_match_the_version_pinned_ports(self):
        # FreeBSD also ships py312-ansible-core221 etc.  Those are DIFFERENT
        # packages and must not be mistaken for the default one.
        assert (
            prereq.find_installed(
                [pkg("py312-ansible-core221", "2.21.1")], "py3*-ansible-core"
            )
            is None
        )

    def test_no_match_returns_none(self):
        assert prereq.find_installed([pkg("nginx", "1.0")], "ansible-core") is None

    def test_empty_inventory_is_handled(self):
        assert prereq.find_installed([], "ansible-core") is None
        assert prereq.find_installed(None, "ansible-core") is None


class TestEvaluate:
    def test_windows_is_not_required_rather_than_satisfied(self):
        # The distinction matters to the UI: nobody installed anything, the
        # executor ships with the agent.
        result = prereq.evaluate(host("Windows"))
        assert result["status"] == prereq.STATUS_NOT_REQUIRED
        assert result["executor"] == "dsc"
        assert result["can_install"] is False
        assert result["detail"] == "bundled_with_agent"

    def test_missing_on_a_supported_platform_offers_install(self):
        result = prereq.evaluate(host("Linux", "Ubuntu 24.04"), [pkg("nginx", "1.0")])
        assert result["status"] == prereq.STATUS_MISSING
        assert result["can_install"] is True
        assert result["package_pattern"] == "ansible-core"

    def test_installed_and_current_is_satisfied_with_no_button(self):
        result = prereq.evaluate(host("OpenBSD"), [pkg("ansible-core", "2.20.4")])
        assert result["status"] == prereq.STATUS_SATISFIED
        assert result["installed_version"] == "2.20.4"
        assert result["can_install"] is False

    def test_installed_but_below_the_floor_is_distinct_from_missing(self):
        result = prereq.evaluate(
            host("Linux", "Ubuntu 24.04"), [pkg("ansible-core", "2.18.16")]
        )
        assert result["status"] == prereq.STATUS_TOO_OLD
        assert result["installed_version"] == "2.18.16"
        # Still offers the remedy: every platform packages >= the floor today.
        assert result["can_install"] is True

    def test_unknown_platform_is_unsupported_not_missing(self):
        # Offering an install button here would dispatch a plan we already
        # know cannot work.
        result = prereq.evaluate(host("Linux", "SomeVendorOS 1.0"), [])
        assert result["status"] == prereq.STATUS_UNSUPPORTED
        assert result["can_install"] is False

    def test_freebsd_satisfied_via_the_globbed_package(self):
        result = prereq.evaluate(host("FreeBSD"), [pkg("py312-ansible-core", "2.21.1")])
        assert result["status"] == prereq.STATUS_SATISFIED
        assert result["package_name"] == "py312-ansible-core"

    def test_macos_matches_the_brew_bundle_name(self):
        result = prereq.evaluate(host("Darwin"), [pkg("ansible", "2.21.3")])
        assert result["status"] == prereq.STATUS_SATISFIED

    def test_every_status_carries_the_executor(self):
        for h, packages in [
            (host("Windows"), []),
            (host("Linux", "Ubuntu 24.04"), []),
            (host("OpenBSD"), [pkg("ansible-core", "2.20.4")]),
            (host("Linux", "SomeVendorOS"), []),
        ]:
            assert prereq.evaluate(h, packages)["executor"] in ("dsc", "ansible-core")
