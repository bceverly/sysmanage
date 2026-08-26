# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the Phase 20.1 config-management prerequisite plan builder."""

import pytest

from backend.services import config_mgmt_plan_builder as builder


def host(platform, release=""):
    return {"platform": platform, "platform_release": release}


class TestExecutorSelection:
    """Which executor a platform gets, and whether it needs installing."""

    @pytest.mark.parametrize(
        "platform",
        ["Windows", "windows", "Windows Server 2022", "WIN32"],
    )
    def test_windows_uses_dsc_and_needs_no_install(self, platform):
        # dsc.exe is vendored with the agent, so a Windows host is ready as
        # soon as the agent is.  Offering an install button there would be
        # offering a no-op.
        assert builder.executor_for(host(platform)) == "dsc"
        assert builder.requires_install(host(platform)) is False
        assert builder.build_install_plan(host(platform)) is None

    @pytest.mark.parametrize(
        "platform", ["Linux", "FreeBSD", "OpenBSD", "NetBSD", "Darwin"]
    )
    def test_every_posix_platform_uses_ansible_and_needs_install(self, platform):
        assert builder.executor_for(host(platform)) == "ansible-core"
        assert builder.requires_install(host(platform)) is True


class TestMeasuredPackageNames:
    """The names came from real boxes; guessing them was wrong twice."""

    def test_openbsd_installs_core_not_the_full_bundle(self):
        # `pkg_add ansible` pulls ansible 13.x/14.x, ~100 collections we do
        # not need.  The standalone core package is the target.
        plan = builder.build_install_plan(host("OpenBSD"))
        assert plan["packages"] == ["ansible-core"]

    def test_netbsd_installs_core_not_the_full_bundle(self):
        plan = builder.build_install_plan(host("NetBSD"))
        assert plan["packages"] == ["ansible-core"]

    def test_freebsd_globs_the_python_prefix_rather_than_pinning_it(self):
        # The prefix tracks FreeBSD's default Python (py312 today).  Pinning
        # it is exactly how the first probe draft broke, so the plan must not
        # contain a literal py NNN.
        plan = builder.build_install_plan(host("FreeBSD"))
        argv = plan["commands"][0]["argv"]
        assert "-g" in argv, "must use pkg's glob matching"
        assert "py3*-ansible-core" in argv
        assert not any("py312" in a or "py311" in a for a in argv)

    def test_freebsd_install_is_non_interactive(self):
        # There is no operator at the far end to answer a prompt.
        assert (
            "-y" in builder.build_install_plan(host("FreeBSD"))["commands"][0]["argv"]
        )

    def test_macos_installs_ansible_because_brew_has_no_core_formula(self):
        plan = builder.build_install_plan(host("Darwin"))
        assert plan["packages"] == [{"manager": "brew", "name": "ansible"}]

    def test_macos_goes_through_the_agents_brew_path_not_a_raw_command(self):
        # The macOS agent is a LaunchDaemon with no UserName key, so it runs as
        # ROOT, and Homebrew refuses to run as root.  A raw `brew install`
        # command step would therefore fail on every Mac.  The agent's package
        # path already drops to the Homebrew prefix owner (`sudo -u <owner>`),
        # so the plan must hand macOS to that rather than shelling out itself.
        plan = builder.build_install_plan(host("Darwin"))
        assert "commands" not in plan

    def test_freebsd_needs_a_command_step_because_the_agent_drops_the_glob(self):
        # `_install_with_pkg` runs `pkg install -y <name>` with no `-g`, so a
        # glob handed to the `packages` path would be taken literally and match
        # nothing.  FreeBSD is the one platform that has to shell out.
        plan = builder.build_install_plan(host("FreeBSD"))
        assert "packages" not in plan
        assert plan["commands"]

    def test_freebsd_does_use_sudo(self):
        assert (
            builder.build_install_plan(host("FreeBSD"))["commands"][0]["sudo"] is True
        )


class TestLinuxFamilies:
    @pytest.mark.parametrize(
        "release,expected_manager",
        [
            ("Ubuntu 24.04", "apt"),
            ("Debian 12", "apt"),
            ("Fedora 41", "dnf"),
            ("Rocky Linux 9", "dnf"),
            ("AlmaLinux 9", "dnf"),
            ("openSUSE Leap 15.6", "zypper"),
            ("Alpine Linux 3.20", "apk"),
        ],
    )
    def test_distro_maps_to_its_package_manager(self, release, expected_manager):
        plan = builder.build_install_plan(host("Linux", release))
        assert plan["packages"][0]["manager"] == expected_manager

    def test_opensuse_uses_the_ansible_package_not_ansible_core(self):
        # openSUSE packages it under the bare name; every other family has
        # ansible-core.
        plan = builder.build_install_plan(host("Linux", "openSUSE Leap 15.6"))
        assert plan["packages"][0]["name"] == "ansible"

    @pytest.mark.parametrize(
        "release", ["Ubuntu 24.04", "Fedora 41", "Alpine Linux 3.20"]
    )
    def test_non_suse_families_use_ansible_core(self, release):
        plan = builder.build_install_plan(host("Linux", release))
        assert plan["packages"][0]["name"] == "ansible-core"

    def test_an_unknown_linux_returns_no_plan_rather_than_a_wrong_one(self):
        # Firing the wrong package manager fails at the far end and looks like
        # a product bug.  Returning None lets the caller say "not available
        # here", which is true and actionable.
        assert builder.build_install_plan(host("Linux", "SomeVendorOS 1.0")) is None


class TestPlanShape:
    """The plan must match what the agent's apply_deployment_plan accepts."""

    @pytest.mark.parametrize(
        "platform,release",
        [
            ("Linux", "Ubuntu 24.04"),
            ("FreeBSD", ""),
            ("OpenBSD", ""),
            ("NetBSD", ""),
            ("Darwin", ""),
        ],
    )
    def test_plans_only_use_keys_the_agent_understands(self, platform, release):
        plan = builder.build_install_plan(host(platform, release))
        allowed = {
            "platform",
            "executor",
            "packages",
            "packages_to_remove",
            "files",
            "commands",
            "service_actions",
        }
        assert set(plan) <= allowed, f"unknown plan keys: {set(plan) - allowed}"

    @pytest.mark.parametrize("platform", ["FreeBSD"])
    def test_command_steps_carry_the_fields_the_executor_reads(self, platform):
        for step in builder.build_install_plan(host(platform))["commands"]:
            assert isinstance(step["argv"], list) and step["argv"]
            assert isinstance(step["sudo"], bool)
            assert step["timeout"] > 0
            assert step["description"]

    def test_no_plan_shells_out(self):
        # The content-lifecycle work established this: argv only, never
        # `sh -c`, so nothing can be injected through a package name.
        for platform in ("FreeBSD",):
            for step in builder.build_install_plan(host(platform))["commands"]:
                assert step["argv"][0] not in ("sh", "bash", "cmd", "powershell")
                assert not any("&&" in a or ";" in a or "|" in a for a in step["argv"])


class TestFloor:
    def test_the_declared_floor_matches_what_platforms_actually_package(self):
        # Every platform measured on 2026-08-26 shipped 2.20 or newer, which
        # is what lets the executor require >= 2.20 without stranding anyone.
        assert builder.MIN_ANSIBLE_CORE == "2.20"

    def test_install_matrix_covers_every_platform_the_agent_ships_on(self):
        platforms = {row["platform"] for row in builder.install_targets()}
        for expected in ("freebsd", "openbsd", "netbsd", "darwin", "windows"):
            assert expected in platforms
