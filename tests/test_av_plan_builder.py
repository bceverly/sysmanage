"""Tests for the open-source AV plan builder."""

from backend.services.av_plan_builder import (
    build_deploy_plan,
    build_enable_plan,
    build_remove_plan,
)

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------


def test_deploy_ubuntu_installs_apt_clamav_and_ships_clamd_conf():
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        antivirus_package="clamav",
    )
    assert plan["av_product"] == "clamav"
    assert "clamav" in plan["packages"]
    assert "clamav-daemon" in plan["packages"]
    paths = [f["path"] for f in plan["files"]]
    assert "/etc/clamav/clamd.conf" in paths
    assert "/etc/clamav/freshclam.conf" in paths
    services = [a for a in plan["service_actions"]]
    assert {"service": "clamav-daemon", "action": "start"} in services


def test_deploy_rocky_pulls_in_epel_and_uses_clamd_at_scan():
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "Rocky 9"},
        antivirus_package="clamav",
    )
    assert "epel-release" in plan["packages"]
    assert "/etc/clamd.d/scan.conf" in [f["path"] for f in plan["files"]]
    services = [a["service"] for a in plan["service_actions"]]
    assert "clamd@scan" in services


def test_deploy_freebsd_uses_pkg_manager():
    plan = build_deploy_plan({"platform": "FreeBSD"}, antivirus_package="clamav")
    assert plan["packages"][0]["manager"] == "pkg"
    assert "/usr/local/etc/clamd.conf" in [f["path"] for f in plan["files"]]
    services = [a["service"] for a in plan["service_actions"]]
    assert "clamav_clamd" in services


def test_deploy_windows_uses_chocolatey_and_writes_clamwin_conf():
    plan = build_deploy_plan({"platform": "Windows"}, antivirus_package="clamwin")
    assert plan["av_product"] == "clamwin"
    assert plan["packages"][0]["manager"] == "chocolatey"
    assert plan["files"][0]["path"].endswith(r"\bin\ClamWin.conf")
    assert "[ClamAV]" in plan["files"][0]["content"]


def test_deploy_caller_supplied_package_is_appended_when_unknown_distro():
    """If caller passes a package not in our distro defaults, we still include it."""
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "Gentoo 23"},
        antivirus_package="some-custom-clam",
    )
    assert "some-custom-clam" in plan["packages"]


def test_deploy_emits_freshclam_to_refresh_definitions_on_linux():
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        antivirus_package="clamav",
    )
    fresh_cmds = [c for c in plan["commands"] if c["argv"] == ["freshclam"]]
    assert len(fresh_cmds) == 1


# ---------------------------------------------------------------------------
# Enable
# ---------------------------------------------------------------------------


def test_enable_ubuntu_starts_existing_services():
    plan = build_enable_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    actions = [(a["service"], a["action"]) for a in plan["service_actions"]]
    assert ("clamav-daemon", "start") in actions
    assert ("clamav-freshclam", "start") in actions
    # No package install on enable.
    assert "packages" not in plan or not plan.get("packages")


def test_enable_rocky_uses_clamd_at_scan():
    plan = build_enable_plan({"platform": "Linux", "platform_release": "Rocky 9"})
    services = [a["service"] for a in plan["service_actions"]]
    assert "clamd@scan" in services


def test_enable_windows_runs_freshclam_only():
    plan = build_enable_plan({"platform": "Windows"})
    assert plan["service_actions"] == []
    assert any("freshclam.exe" in c["argv"][0] for c in plan["commands"])


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


def test_remove_ubuntu_stops_services_then_removes_packages():
    plan = build_remove_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    actions = [(a["service"], a["action"]) for a in plan["service_actions"]]
    assert ("clamav-daemon", "stop") in actions
    assert ("clamav-daemon", "disable") in actions
    assert "clamav-daemon" in plan["packages_to_remove"]


def test_remove_rocky_does_not_uninstall_epel_release():
    plan = build_remove_plan({"platform": "Linux", "platform_release": "Rocky 9"})
    assert "epel-release" not in plan["packages_to_remove"]
    assert "clamd" in plan["packages_to_remove"]


def test_remove_freebsd_uses_pkg_manager():
    plan = build_remove_plan({"platform": "FreeBSD"})
    pkgs = plan["packages_to_remove"]
    assert pkgs[0]["manager"] == "pkg"


def test_remove_windows_uses_chocolatey():
    plan = build_remove_plan({"platform": "Windows"})
    pkgs = plan["packages_to_remove"]
    assert pkgs[0]["manager"] == "chocolatey"
    assert pkgs[0]["name"] == "clamwin"
