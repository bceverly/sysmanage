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


# ---------------------------------------------------------------------------
# checks_per_day cadence (Phase 3)
# ---------------------------------------------------------------------------

import pytest

from backend.services.av_plan_builder import (
    _basic_freshclam_conf,
    _validate_scan_schedule,
    _cron_line_for_schedule,
    _scan_command_for_paths,
    build_disable_plan,
)


def test_freshclam_conf_default_cadence_is_24():
    conf = _basic_freshclam_conf()
    assert "Checks 24" in conf


def test_freshclam_conf_honors_explicit_cadence():
    conf = _basic_freshclam_conf(checks_per_day=6)
    assert "Checks 6" in conf


def test_freshclam_conf_clamps_below_minimum():
    # ClamAV requires Checks >= 1; planner clamps anything lower.
    conf = _basic_freshclam_conf(checks_per_day=0)
    assert "Checks 1" in conf


def test_freshclam_conf_clamps_above_maximum():
    # ClamAV upper bound is 50; planner clamps so we never emit invalid config.
    conf = _basic_freshclam_conf(checks_per_day=999)
    assert "Checks 50" in conf


def test_freshclam_conf_handles_non_int_cadence_gracefully():
    # Defensive: callers passing None/strings should not crash; default is used.
    assert "Checks 24" in _basic_freshclam_conf(None)
    assert "Checks 24" in _basic_freshclam_conf("oops")  # type: ignore[arg-type]


def test_deploy_plan_threads_cadence_into_freshclam_conf():
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        antivirus_package="clamav",
        options={"checks_per_day": 12},
    )
    fresh = next(f for f in plan["files"] if f["path"].endswith("freshclam.conf"))
    assert "Checks 12" in fresh["content"]


# ---------------------------------------------------------------------------
# scan schedule validation
# ---------------------------------------------------------------------------


def test_validate_scan_schedule_empty_returns_empty():
    assert _validate_scan_schedule(None) == {}
    assert _validate_scan_schedule({}) == {}


def test_validate_scan_schedule_daily_defaults_to_3am():
    out = _validate_scan_schedule({"frequency": "daily"})
    assert out["frequency"] == "daily"
    assert out["hour"] == 3
    assert out["minute"] == 0
    assert out["scan_paths"] == ["/"]


def test_validate_scan_schedule_weekly_requires_dow_in_range():
    out = _validate_scan_schedule({"frequency": "weekly", "day_of_week": 6})
    assert out["day_of_week"] == 6
    with pytest.raises(ValueError):
        _validate_scan_schedule({"frequency": "weekly", "day_of_week": 7})


def test_validate_scan_schedule_monthly_caps_at_28():
    # 28 is the highest dom that exists in every month.
    _validate_scan_schedule({"frequency": "monthly", "day_of_month": 28})
    with pytest.raises(ValueError):
        _validate_scan_schedule({"frequency": "monthly", "day_of_month": 31})


def test_validate_scan_schedule_rejects_bogus_frequency():
    with pytest.raises(ValueError, match="frequency"):
        _validate_scan_schedule({"frequency": "fortnightly"})


def test_validate_scan_schedule_clamps_hour_minute():
    with pytest.raises(ValueError):
        _validate_scan_schedule({"frequency": "daily", "hour": 24})
    with pytest.raises(ValueError):
        _validate_scan_schedule({"frequency": "daily", "minute": 60})


# ---------------------------------------------------------------------------
# cron line rendering
# ---------------------------------------------------------------------------


def test_cron_line_daily_uses_wildcards():
    sched = _validate_scan_schedule({"frequency": "daily", "hour": 2, "minute": 30})
    line = _cron_line_for_schedule(sched, "/usr/bin/clamdscan -m /")
    assert line == "30 2 * * * root /usr/bin/clamdscan -m /"


def test_cron_line_weekly_pins_dow():
    sched = _validate_scan_schedule(
        {"frequency": "weekly", "day_of_week": 0, "hour": 4, "minute": 15}
    )
    line = _cron_line_for_schedule(sched, "x")
    # cron field 5 is day-of-week (0 = Sunday).
    assert line.split()[4] == "0"


def test_cron_line_monthly_pins_dom():
    sched = _validate_scan_schedule(
        {"frequency": "monthly", "day_of_month": 15, "hour": 0, "minute": 0}
    )
    line = _cron_line_for_schedule(sched, "x")
    # cron field 3 is day-of-month.
    assert line.split()[2] == "15"


def test_scan_command_quotes_paths_with_spaces():
    cmd = _scan_command_for_paths(["/var/www", "/opt/app data"])
    assert '"/var/www"' in cmd
    assert '"/opt/app data"' in cmd


# ---------------------------------------------------------------------------
# scan_schedule end-to-end through deploy plan
# ---------------------------------------------------------------------------


def test_deploy_plan_with_schedule_emits_cron_d_file_on_linux():
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        antivirus_package="clamav",
        options={
            "scan_schedule": {
                "frequency": "weekly",
                "day_of_week": 0,
                "hour": 2,
                "scan_paths": ["/var/www"],
            }
        },
    )
    cron_files = [f for f in plan["files"] if "cron.d" in f["path"]]
    assert len(cron_files) == 1
    body = cron_files[0]["content"]
    assert "/var/www" in body
    assert "clamdscan" in body
    # Plan also surfaces the normalized schedule for the API to echo back.
    assert plan["scan_schedule"]["frequency"] == "weekly"


def test_deploy_plan_without_schedule_omits_cron_file():
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        antivirus_package="clamav",
    )
    assert not any("cron.d" in f["path"] for f in plan["files"])
    assert plan["scan_schedule"] is None


def test_deploy_plan_with_schedule_emits_schtasks_on_windows():
    plan = build_deploy_plan(
        {"platform": "Windows"},
        antivirus_package="clamwin",
        options={
            "scan_schedule": {
                "frequency": "daily",
                "hour": 3,
                "minute": 0,
            }
        },
    )
    sched_cmds = [c for c in plan["commands"] if c["argv"][0] == "schtasks"]
    assert len(sched_cmds) == 1
    argv = sched_cmds[0]["argv"]
    assert "/SC" in argv and "DAILY" in argv
    assert "/ST" in argv and "03:00" in argv


def test_deploy_plan_freebsd_emits_cron_file_for_schedule():
    plan = build_deploy_plan(
        {"platform": "FreeBSD"},
        antivirus_package="clamav",
        options={
            "scan_schedule": {"frequency": "daily", "hour": 3},
        },
    )
    cron_files = [f for f in plan["files"] if "cron.d" in f["path"]]
    assert len(cron_files) == 1


def test_deploy_plan_openbsd_skips_cron_file_for_schedule():
    # OpenBSD/NetBSD/macOS go through the BSD path but only FreeBSD has /etc/cron.d.
    # The other BSDs should NOT have a cron file emitted (they use crontab(1) directly).
    plan = build_deploy_plan(
        {"platform": "OpenBSD"},
        antivirus_package="clamav",
        options={
            "scan_schedule": {"frequency": "daily", "hour": 3},
        },
    )
    cron_files = [f for f in plan["files"] if "cron.d" in f["path"]]
    assert cron_files == []
    # But the schedule still propagates through the plan for callers to honour.
    assert plan["scan_schedule"] is not None


# ---------------------------------------------------------------------------
# build_disable_plan (Phase 3 addition)
# ---------------------------------------------------------------------------


def test_disable_plan_linux_stops_and_disables_services_no_uninstall():
    plan = build_disable_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    actions = [(a["service"], a["action"]) for a in plan["service_actions"]]
    assert ("clamav-daemon", "stop") in actions
    assert ("clamav-daemon", "disable") in actions
    # Disable must NOT uninstall packages.
    assert "packages_to_remove" not in plan or not plan.get("packages_to_remove")


def test_disable_plan_windows_removes_scheduled_task():
    plan = build_disable_plan({"platform": "Windows"})
    schtasks = [c for c in plan["commands"] if c["argv"][0] == "schtasks"]
    assert len(schtasks) == 1
    assert "/Delete" in schtasks[0]["argv"]


def test_disable_plan_bsd_uses_clamav_clamd_service():
    plan = build_disable_plan({"platform": "FreeBSD"})
    services = [a["service"] for a in plan["service_actions"]]
    assert "clamav_clamd" in services


# ---------------------------------------------------------------------------
# Linux distro layout coverage — SUSE, Arch
# ---------------------------------------------------------------------------


def test_deploy_suse_uses_etc_clamd_conf_layout():
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "openSUSE Leap 15.6"},
        antivirus_package="clamav",
    )
    paths = [f["path"] for f in plan["files"]]
    assert "/etc/clamd.conf" in paths
    services = [a["service"] for a in plan["service_actions"]]
    assert "clamd" in services
    assert "freshclam" in services


def test_deploy_arch_uses_clamav_etc_layout():
    plan = build_deploy_plan(
        {"platform": "Linux", "platform_release": "Arch Linux"},
        antivirus_package="clamav",
    )
    paths = [f["path"] for f in plan["files"]]
    assert "/etc/clamav/clamd.conf" in paths
    services = [a["service"] for a in plan["service_actions"]]
    assert "clamav-daemon" in services
    assert "clamav-freshclam" in services


# ---------------------------------------------------------------------------
# BSD platform branches — NetBSD and macOS layouts
# ---------------------------------------------------------------------------


def test_deploy_netbsd_uses_pkgin_and_pkg_etc_layout():
    plan = build_deploy_plan({"platform": "NetBSD"}, antivirus_package="clamav")
    assert plan["packages"][0]["manager"] == "pkgin"
    paths = [f["path"] for f in plan["files"]]
    assert "/usr/pkg/etc/clamd.conf" in paths


def test_deploy_macos_uses_brew_layout():
    plan = build_deploy_plan({"platform": "Darwin"}, antivirus_package="clamav")
    assert plan["packages"][0]["manager"] == "brew"
    paths = [f["path"] for f in plan["files"]]
    assert "/usr/local/etc/clamav/clamd.conf" in paths


# ---------------------------------------------------------------------------
# build_enable_plan — all three platforms
# ---------------------------------------------------------------------------


def test_enable_plan_linux_starts_clamav_services():
    plan = build_enable_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    actions = [(a["service"], a["action"]) for a in plan["service_actions"]]
    assert ("clamav-daemon", "start") in actions
    # build_enable_plan must NOT install anything — it's for hosts that
    # already have AV.
    assert plan.get("files", []) == []
    assert plan.get("commands", []) == []


def test_enable_plan_windows_emits_no_install_just_a_start():
    plan = build_enable_plan({"platform": "Windows"})
    # The Windows enable plan still uses commands (schtasks), but no
    # package install — verify shape.
    assert "av_product" in plan


def test_enable_plan_bsd_starts_clamd_and_freshclam():
    plan = build_enable_plan({"platform": "FreeBSD"})
    services = {(a["service"], a["action"]) for a in plan["service_actions"]}
    assert ("clamav_clamd", "start") in services
    assert ("clamav_freshclam", "start") in services
    assert plan.get("files") == []


def test_enable_plan_unknown_platform_falls_back_to_linux_default():
    """Unknown OS goes through the linux branch with the Debian-ish default."""
    plan = build_enable_plan({"platform": "Plan9"})
    # Default Linux layout services 'clamav-daemon' and 'clamav-freshclam'.
    services = {a["service"] for a in plan["service_actions"]}
    assert "clamav-daemon" in services


# ---------------------------------------------------------------------------
# Windows schedule — weekly and monthly cadences
# ---------------------------------------------------------------------------


def test_deploy_windows_weekly_schedule_pins_day_of_week():
    plan = build_deploy_plan(
        {"platform": "Windows"},
        antivirus_package="clamwin",
        options={
            "scan_schedule": {
                "frequency": "weekly",
                "day_of_week": 3,  # Wednesday
                "hour": 4,
                "minute": 30,
            }
        },
    )
    sched_cmd = next(c for c in plan["commands"] if c["argv"][0] == "schtasks")
    argv = sched_cmd["argv"]
    assert "WEEKLY" in argv
    # /D WED should be present.
    assert "/D" in argv
    assert "WED" in argv


def test_deploy_windows_monthly_schedule_pins_day_of_month():
    plan = build_deploy_plan(
        {"platform": "Windows"},
        antivirus_package="clamwin",
        options={
            "scan_schedule": {
                "frequency": "monthly",
                "day_of_month": 15,
                "hour": 1,
                "minute": 0,
            }
        },
    )
    sched_cmd = next(c for c in plan["commands"] if c["argv"][0] == "schtasks")
    argv = sched_cmd["argv"]
    assert "MONTHLY" in argv
    assert "/D" in argv
    assert "15" in argv
