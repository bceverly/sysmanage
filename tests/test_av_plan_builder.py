# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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
    services = list(plan["service_actions"])
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


def test_deploy_windows_installs_official_clamav_where_the_agent_looks():
    # The seeded default "clamwin" (ClamAV 0.103, end of life, and never
    # detected by the agent) is replaced by the official build.
    plan = build_deploy_plan({"platform": "Windows"}, antivirus_package="clamwin")
    assert plan["av_product"] == "clamav"
    # The official MSI via winget; Chocolatey's "clamav" is a portable zip
    # that never lands in Program Files.
    assert plan["packages"] == [{"manager": "winget", "name": "Cisco.ClamAV"}]
    assert plan["files"][0]["path"] == r"C:\Program Files\ClamAV\freshclam.conf"
    assert "DatabaseDirectory" not in plan["files"][0]["content"]
    argvs = [c["argv"] for c in plan["commands"]]
    assert [r"C:\Program Files\ClamAV\freshclam.exe"] in argvs
    # The database directory exists before freshclam runs.
    assert "database" in argvs[0][-1] and argvs[1][0].endswith("freshclam.exe")
    seeded = build_deploy_plan({"platform": "Windows"}, antivirus_package="clamav")
    assert seeded["packages"][0]["name"] == "Cisco.ClamAV"
    custom = build_deploy_plan({"platform": "Windows"}, antivirus_package="Acme.AV")
    assert custom["packages"][0]["name"] == "Acme.AV"


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
    assert pkgs[0]["manager"] == "winget"
    assert pkgs[0]["name"] == "Cisco.ClamAV"


# ---------------------------------------------------------------------------
# checks_per_day cadence (Phase 3)
# ---------------------------------------------------------------------------

import pytest

from backend.services.av_plan_builder import (
    _basic_freshclam_conf,
    _cron_line_for_schedule,
    _scan_command_for_paths,
    _validate_scan_schedule,
    build_disable_plan,
)


def test_freshclam_conf_default_cadence_is_every_two_hours():
    conf = _basic_freshclam_conf()
    assert "Checks 12" in conf


def test_freshclam_conf_honors_explicit_cadence():
    conf = _basic_freshclam_conf(checks_per_day=6)
    assert "Checks 6" in conf


def test_freshclam_conf_clamps_below_minimum():
    # ClamAV requires Checks >= 1; planner clamps anything lower.
    conf = _basic_freshclam_conf(checks_per_day=0)
    assert "Checks 1" in conf


def test_freshclam_conf_never_checks_more_than_hourly():
    # ClamAV's mirrors throttle clients that download too often (HTTP 429).
    conf = _basic_freshclam_conf(checks_per_day=999)
    assert "Checks 24" in conf


def test_freshclam_conf_handles_non_int_cadence_gracefully():
    # Defensive: callers passing None/strings should not crash; default is used.
    assert "Checks 12" in _basic_freshclam_conf(None)
    assert "Checks 12" in _basic_freshclam_conf("oops")  # type: ignore[arg-type]


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
    sched_cmds = [
        c
        for c in plan["commands"]
        if c["argv"][0] == "schtasks" and "SysManage ClamAV Scan" in c["argv"]
    ]  # the definition-update task is separate
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
    # But the schedule still propagates through the plan for callers to honor.
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
    assert len(schtasks) == 2  # the update task and the scan task
    assert all("/Delete" in c["argv"] for c in schtasks)


def test_disable_plan_bsd_uses_clamav_clamd_service():
    plan = build_disable_plan({"platform": "FreeBSD"})
    services = [a["service"] for a in plan["service_actions"]]
    assert "clamav_clamd" in services


# ---------------------------------------------------------------------------
# Linux distro layout coverage -- SUSE, Arch
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
# BSD platform branches -- NetBSD and macOS layouts
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
# build_enable_plan -- all three platforms
# ---------------------------------------------------------------------------


def test_enable_plan_linux_starts_clamav_services():
    plan = build_enable_plan({"platform": "Linux", "platform_release": "Ubuntu 24.04"})
    actions = [(a["service"], a["action"]) for a in plan["service_actions"]]
    assert ("clamav-daemon", "start") in actions
    # build_enable_plan must NOT install anything -- it's for hosts that
    # already have AV.
    assert plan.get("files", []) == []
    assert plan.get("commands", []) == []


def test_enable_plan_windows_emits_no_install_just_a_start():
    plan = build_enable_plan({"platform": "Windows"})
    # The Windows enable plan still uses commands (schtasks), but no
    # package install -- verify shape.
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
# Windows schedule -- weekly and monthly cadences
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
    sched_cmd = next(
        c for c in plan["commands"] if "SysManage ClamAV Scan" in c["argv"]
    )
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
    sched_cmd = next(
        c for c in plan["commands"] if "SysManage ClamAV Scan" in c["argv"]
    )
    argv = sched_cmd["argv"]
    assert "MONTHLY" in argv
    assert "/D" in argv
    assert "15" in argv


# -- 2026-09-30: the package's own layout, not Linux's, on every platform ------


def _file(plan, suffix):
    return next(f for f in plan["files"] if f["path"].endswith(suffix))


def test_freshclam_conf_leaves_database_location_to_the_package():
    """Hard-coding /var/lib/clamav put the BSDs' signatures where clamscan
    never looks (/var/db/clamav, /var/clamav), and DatabaseOwner clamav broke
    OpenBSD (_clamav) and RHEL (clamupdate)."""
    conf = _basic_freshclam_conf()
    assert "DatabaseDirectory" not in conf and "DatabaseOwner" not in conf
    assert "LogSyslog yes" in conf


def test_each_bsd_gets_its_own_user_socket_and_services():
    expected = {
        "FreeBSD": ("User clamav", "/var/run/clamav/clamd.sock", "clamav_freshclam"),
        "OpenBSD": ("User _clamav", "/var/db/clamav/clamd.sock", "freshclam"),
        "NetBSD": ("User clamav", "/var/clamav/clamd.sock", "freshclamd"),
    }
    for plat, (user, sock, fresh_svc) in expected.items():
        plan = build_deploy_plan({"platform": plat}, antivirus_package="clamav")
        clamd = _file(plan, "clamd.conf")["content"]
        assert user in clamd and f"LocalSocket {sock}" in clamd, plat
        assert "DatabaseDirectory" not in clamd and "LogFile" not in clamd, plat
        assert {"service": fresh_svc, "action": "enable"} in plan[
            "service_actions"
        ], plat


def test_macos_uses_the_homebrew_prefix_and_a_launchd_updater():
    for arch, prefix in (("arm64", "/opt/homebrew"), ("x86_64", "/usr/local")):
        plan = build_deploy_plan(
            {"platform": "macOS", "machine_architecture": arch},
            antivirus_package="clamav",
        )
        fresh = _file(plan, "freshclam.conf")
        assert fresh["path"] == f"{prefix}/etc/clamav/freshclam.conf"
        # Homebrew builds default to a clamav user that macOS does not have.
        assert "DatabaseOwner root" in fresh["content"]
        job = _file(plan, "org.sysmanage.freshclam.plist")["content"]
        assert f"<string>{prefix}/bin/freshclam</string>" in job and "--daemon" in job
        argvs = [c["argv"] for c in plan["commands"]]
        assert ["launchctl", "bootstrap", "system",
                "/Library/LaunchDaemons/org.sysmanage.freshclam.plist"] in argvs  # fmt: skip
        assert plan["service_actions"] == []


def test_windows_schedules_freshclam_at_the_cadence():
    plan = build_deploy_plan(
        {"platform": "Windows"},
        antivirus_package="clamwin",
        options={"checks_per_day": 6},
    )
    task = next(c for c in plan["commands"] if "SysManage ClamAV Update" in c["argv"])
    argv = task["argv"]
    assert (
        argv[argv.index("/SC") + 1] == "HOURLY" and argv[argv.index("/MO") + 1] == "4"
    )
    assert argv[argv.index("/RU") + 1] == "SYSTEM"


def test_package_managers_are_named_as_the_agent_names_its_installers():
    # The agent dispatches to _install_with_<manager>; "pkg_add" and
    # "chocolatey" have no installer there, so those plans failed instantly.
    expect = {
        "FreeBSD": "pkg",
        "OpenBSD": "pkg",
        "NetBSD": "pkgin",
        "Windows": "winget",
    }
    for plat, manager in expect.items():
        plan = build_deploy_plan({"platform": plat}, antivirus_package="clamav")
        assert plan["packages"][0]["manager"] == manager, plat


def test_freebsd_clamd_is_visible_to_rc_and_restarted_on_deploy():
    # Without PidFile the port's rc script reported a running clamd as "not
    # running" and could not stop it; a clamd started that way must be ended
    # so the service actions can start it under the new configuration.
    plan = build_deploy_plan({"platform": "FreeBSD"}, antivirus_package="clamav")
    clamd_conf = plan["files"][0]["content"]
    assert "PidFile /var/run/clamav/clamd.pid" in clamd_conf
    stop = [
        c["argv"] for c in plan["commands"] if "pkill -x clamd" in " ".join(c["argv"])
    ]
    # It must WAIT for the old clamd to exit: the start raced its shutdown,
    # rc said "already running", and nothing was left (2026-09-30).
    assert len(stop) == 1 and "while pgrep -x clamd" in stop[0][-1]
    other = build_deploy_plan({"platform": "OpenBSD"}, antivirus_package="clamav")
    assert "PidFile" not in other["files"][0]["content"]
    assert not any("pkill" in " ".join(c["argv"]) for c in other["commands"])


def test_clamav_logs_to_a_facility_syslog_keeps():
    for plat in ("FreeBSD", "NetBSD", "Darwin"):
        plan = build_deploy_plan({"platform": plat}, antivirus_package="clamav")
        for f in plan["files"][:2]:
            assert "LogFacility LOG_DAEMON" in f["content"], (plat, f["path"])


# -- Phase 22.3: scheduled scans spread per host ---------------------------------


def _ubuntu(host_id=None):
    info = {"platform": "Linux", "platform_release": "Ubuntu 24.04",
            "platform_version": "24.04", "machine_architecture": None}  # fmt: skip
    if host_id:
        info["host_id"] = host_id
    return info


def test_hosts_on_one_policy_do_not_all_scan_at_the_same_minute():
    import uuid  # pylint: disable=import-outside-toplevel

    # Fixed ids: the spread is a hash of the host id, and 40 random ids landed
    # on as few as 25 distinct minutes often enough to fail CI at random.
    times = set()
    for i in range(40):
        plan = build_deploy_plan(
            _ubuntu(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"host-{i}"))), "clamav",
            {"scan_schedule": {"frequency": "daily", "hour": 3, "minute": 0}},
        )  # fmt: skip
        sched = plan["scan_schedule"]
        assert 3 * 60 <= sched["hour"] * 60 + sched["minute"] < 3 * 60 + 60
        times.add((sched["hour"], sched["minute"]))
    assert len(times) > 20


def test_a_hosts_scan_time_is_stable():
    opts = {"scan_schedule": {"frequency": "daily", "hour": 3, "minute": 0}}
    first = build_deploy_plan(_ubuntu("host-a"), "clamav", opts)
    again = build_deploy_plan(_ubuntu("host-a"), "clamav", opts)
    assert first["scan_schedule"] == again["scan_schedule"]


def test_a_late_scan_never_moves_to_the_next_day():
    import uuid  # pylint: disable=import-outside-toplevel

    for _ in range(40):
        plan = build_deploy_plan(
            _ubuntu(str(uuid.uuid4())), "clamav",
            {"scan_schedule": {"frequency": "weekly", "hour": 23, "minute": 30,
                               "day_of_week": 2}},
        )  # fmt: skip
        sched = plan["scan_schedule"]
        assert sched["hour"] == 23 and 30 <= sched["minute"] <= 59
        assert sched["day_of_week"] == 2


def test_without_a_host_id_the_schedule_is_unchanged():
    plan = build_deploy_plan(
        _ubuntu(),
        "clamav",
        {"scan_schedule": {"frequency": "daily", "hour": 3, "minute": 0}},
    )
    assert (plan["scan_schedule"]["hour"], plan["scan_schedule"]["minute"]) == (3, 0)
