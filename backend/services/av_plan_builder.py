"""
Free-tier (open-source) antivirus plan builder.

Generates declarative AV deployment plans for the 3 basic operations the
open-source server supports: deploy, enable, remove. Plans use the same
shape that the Pro+ av_management_engine emits.

For deploy, the plan installs the OS-default antivirus package, drops a
basic clamd.conf + freshclam.conf, refreshes the signature database,
and enables the relevant services. Pro+ licensees get the richer engine
in sysmanage-professional-plus/module-source/av_management_engine which
adds tenant policies, scheduled scans, scan-result aggregation, and
commercial-AV detection.
"""

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Conf-file paths used by multiple distro layouts (deduped to satisfy
# Sonar's duplicate-string-literal rule).
# ---------------------------------------------------------------------------

CLAMD_CONF_DEBIAN = "/etc/clamav/clamd.conf"
FRESHCLAM_CONF_DEBIAN = "/etc/clamav/freshclam.conf"
FRESHCLAM_CONF_RPM = "/etc/freshclam.conf"

# ---------------------------------------------------------------------------
# Distro / platform → packages, paths, services
# ---------------------------------------------------------------------------


def _linux_clamav_layout(distro: str) -> Tuple[List[str], str, str, str, str]:
    """Returns (packages, clamd_conf, freshclam_conf, clamd_service, freshclam_service)."""
    d = (distro or "").lower()
    if "ubuntu" in d or "debian" in d:
        return (
            ["clamav", "clamav-daemon", "clamav-freshclam"],
            CLAMD_CONF_DEBIAN,
            FRESHCLAM_CONF_DEBIAN,
            "clamav-daemon",
            "clamav-freshclam",
        )
    if any(
        k in d
        for k in ("rhel", "centos", "rocky", "alma", "oracle", "fedora", "amazon")
    ):
        return (
            ["epel-release", "clamav", "clamd", "clamav-update"],
            "/etc/clamd.d/scan.conf",
            FRESHCLAM_CONF_RPM,
            "clamd@scan",
            "clamav-freshclam",
        )
    if "suse" in d or "sles" in d:
        return (
            ["clamav", "clamav-freshclam", "clamav-daemon"],
            "/etc/clamd.conf",
            FRESHCLAM_CONF_RPM,
            "clamd",
            "freshclam",
        )
    if "arch" in d or "manjaro" in d:
        return (
            ["clamav"],
            CLAMD_CONF_DEBIAN,
            FRESHCLAM_CONF_DEBIAN,
            "clamav-daemon",
            "clamav-freshclam",
        )
    # Reasonable Debian-family default for unknown distros
    return (
        ["clamav", "clamav-daemon", "clamav-freshclam"],
        CLAMD_CONF_DEBIAN,
        FRESHCLAM_CONF_DEBIAN,
        "clamav-daemon",
        "clamav-freshclam",
    )


def _bsd_clamav_layout(plat: str) -> Tuple[str, str, str, str, str]:
    """Returns (pkg_manager, clamd_conf, freshclam_conf, clamd_service, freshclam_service)."""
    p = (plat or "").lower()
    if p == "freebsd":
        return (
            "pkg",
            "/usr/local/etc/clamd.conf",
            "/usr/local/etc/freshclam.conf",
            "clamav_clamd",
            "clamav_freshclam",
        )
    if p == "openbsd":
        return (
            "pkg_add",
            "/etc/clamd.conf",
            "/etc/freshclam.conf",
            "clamd",
            "freshclam",
        )
    if p == "netbsd":
        return (
            "pkgin",
            "/usr/pkg/etc/clamd.conf",
            "/usr/pkg/etc/freshclam.conf",
            "clamd",
            "freshclam",
        )
    # darwin / macos
    return (
        "brew",
        "/usr/local/etc/clamav/clamd.conf",
        "/usr/local/etc/clamav/freshclam.conf",
        "clamav",
        "clamav-freshclam",
    )


def _basic_clamd_conf() -> str:
    return (
        "# clamd.conf - managed by sysmanage open-source AV planner\n"
        "# DO NOT EDIT MANUALLY - overwrites on every deploy\n"
        "\n"
        "LogFile /var/log/clamav/clamav.log\n"
        "LogTime yes\n"
        "PidFile /var/run/clamav/clamd.pid\n"
        "LocalSocket /var/run/clamav/clamd.ctl\n"
        "FixStaleSocket yes\n"
        "User clamav\n"
        "ScanMail yes\n"
        "ScanArchive yes\n"
        "MaxThreads 12\n"
        "MaxFileSize 100M\n"
        "MaxScanSize 400M\n"
        "DatabaseDirectory /var/lib/clamav\n"
    )


def _basic_freshclam_conf(checks_per_day: Optional[int] = None) -> str:
    """
    Render freshclam.conf with a configurable definition-update cadence.

    `checks_per_day` defaults to 24 (every hour) if not supplied. ClamAV
    accepts 1-50; we clamp anything outside that range so we never emit
    an unparseable config.
    """
    cadence = checks_per_day if isinstance(checks_per_day, int) else 24
    cadence = max(cadence, 1)
    cadence = min(cadence, 50)
    return (
        "# freshclam.conf - managed by sysmanage open-source AV planner\n"
        "# DO NOT EDIT MANUALLY - overwrites on every deploy\n"
        "\n"
        "DatabaseOwner clamav\n"
        "UpdateLogFile /var/log/clamav/freshclam.log\n"
        "DatabaseMirror database.clamav.net\n"
        f"Checks {cadence}\n"
        "DatabaseDirectory /var/lib/clamav\n"
    )


# ---------------------------------------------------------------------------
# Scan schedule helpers
# ---------------------------------------------------------------------------


def _validate_scan_schedule(schedule: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize a scan-schedule dict.

    Accepted shape:
        {
          "frequency": "daily" | "weekly" | "monthly",
          "hour":   int 0-23   (default 3)
          "minute": int 0-59   (default 0)
          "day_of_week": int 0-6  (only used when frequency=weekly; 0=Sunday)
          "day_of_month": int 1-28  (only used when frequency=monthly; capped
                                     at 28 so February doesn't drop scans)
          "scan_paths": [str, ...]  (default ["/"])
        }

    Returns the normalized dict, or {} if schedule is falsy. Raises ValueError
    on invalid inputs so the caller fails loudly instead of silently building
    a broken cron line.
    """
    if not schedule:
        return {}

    frequency = (schedule.get("frequency") or "daily").lower()
    if frequency not in ("daily", "weekly", "monthly"):
        raise ValueError(
            f"scan schedule frequency must be daily|weekly|monthly, got {frequency!r}"
        )

    hour = int(schedule.get("hour", 3))
    minute = int(schedule.get("minute", 0))
    if not 0 <= hour <= 23:
        raise ValueError(f"scan schedule hour must be 0-23, got {hour}")
    if not 0 <= minute <= 59:
        raise ValueError(f"scan schedule minute must be 0-59, got {minute}")

    out: Dict[str, Any] = {
        "frequency": frequency,
        "hour": hour,
        "minute": minute,
        "scan_paths": list(schedule.get("scan_paths") or ["/"]),
    }

    if frequency == "weekly":
        dow = int(schedule.get("day_of_week", 0))
        if not 0 <= dow <= 6:
            raise ValueError(f"day_of_week must be 0-6, got {dow}")
        out["day_of_week"] = dow
    elif frequency == "monthly":
        dom = int(schedule.get("day_of_month", 1))
        if not 1 <= dom <= 28:
            raise ValueError(
                f"day_of_month must be 1-28 (we clamp at 28 to keep months consistent), got {dom}"
            )
        out["day_of_month"] = dom

    return out


def _cron_line_for_schedule(schedule: Dict[str, Any], scan_command: str) -> str:
    """Render one /etc/cron.d-style line from a normalized schedule dict."""
    minute = schedule["minute"]
    hour = schedule["hour"]
    if schedule["frequency"] == "daily":
        return f"{minute} {hour} * * * root {scan_command}"
    if schedule["frequency"] == "weekly":
        return f"{minute} {hour} * * {schedule['day_of_week']} root {scan_command}"
    # monthly
    return f"{minute} {hour} {schedule['day_of_month']} * * root {scan_command}"


def _scan_command_for_paths(scan_paths: List[str]) -> str:
    """
    Render the on-host scan command. `clamdscan -m` uses the running clamd
    daemon, falling back to `clamscan` (slower) is the operator's call —
    we keep it simple here.
    """
    quoted = " ".join(f'"{p}"' for p in scan_paths)
    return f"/usr/bin/clamdscan -m --fdpass {quoted}"


# ---------------------------------------------------------------------------
# Per-platform deploy / enable / remove
# ---------------------------------------------------------------------------


def _linux_deploy(
    host_info: Dict[str, Any],
    antivirus_package: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a Linux AV deploy plan.

    `options` may carry:
        checks_per_day: int (1-50) — freshclam definition-update cadence
        scan_schedule:  dict — see _validate_scan_schedule. When set, an
                       /etc/cron.d/sysmanage-clamscan file is added to
                       the plan with a cron entry that invokes clamdscan
                       on the configured paths and frequency.
    """
    options = options or {}
    distro = (host_info.get("platform_release") or "").lower()
    pkgs, clamd_conf, fresh_conf, clamd_svc, fresh_svc = _linux_clamav_layout(distro)
    if antivirus_package and antivirus_package not in pkgs:
        # Caller's choice of package wins — the OS defaults table may
        # specify something distro-specific.
        pkgs = list(pkgs) + [antivirus_package]

    files: List[Dict[str, Any]] = [
        {
            "path": clamd_conf,
            "content": _basic_clamd_conf(),
            "mode": 0o644,
            "owner": "root",
            "group": "root",
            "backup": True,
        },
        {
            "path": fresh_conf,
            "content": _basic_freshclam_conf(options.get("checks_per_day")),
            "mode": 0o644,
            "owner": "root",
            "group": "root",
            "backup": True,
        },
    ]

    schedule = _validate_scan_schedule(options.get("scan_schedule"))
    if schedule:
        scan_cmd = _scan_command_for_paths(schedule["scan_paths"])
        cron_line = _cron_line_for_schedule(schedule, scan_cmd)
        files.append(
            {
                "path": "/etc/cron.d/sysmanage-clamscan",
                "content": (
                    "# Managed by sysmanage av_plan_builder — DO NOT EDIT\n"
                    "SHELL=/bin/sh\n"
                    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
                    f"{cron_line}\n"
                ),
                "mode": 0o644,
                "owner": "root",
                "group": "root",
                "backup": True,
            }
        )

    return {
        "platform": "linux",
        "av_product": "clamav",
        "distro": distro,
        "packages": pkgs,
        "files": files,
        "commands": [
            {
                "argv": ["freshclam"],
                "sudo": True,
                "timeout": 300,
                "ignore_errors": True,
                "description": "refresh ClamAV signature database",
            },
        ],
        "service_actions": [
            {"service": fresh_svc, "action": "enable"},
            {"service": fresh_svc, "action": "start"},
            {"service": clamd_svc, "action": "enable"},
            {"service": clamd_svc, "action": "start"},
        ],
        "scan_schedule": schedule or None,
    }


def _linux_enable(host_info: Dict[str, Any]) -> Dict[str, Any]:
    distro = (host_info.get("platform_release") or "").lower()
    _, _, _, clamd_svc, fresh_svc = _linux_clamav_layout(distro)
    return {
        "platform": "linux",
        "av_product": "clamav",
        "files": [],
        "commands": [],
        "service_actions": [
            {"service": fresh_svc, "action": "enable"},
            {"service": fresh_svc, "action": "start"},
            {"service": clamd_svc, "action": "enable"},
            {"service": clamd_svc, "action": "start"},
        ],
    }


def _linux_remove(host_info: Dict[str, Any]) -> Dict[str, Any]:
    distro = (host_info.get("platform_release") or "").lower()
    pkgs, _, _, clamd_svc, fresh_svc = _linux_clamav_layout(distro)
    # Don't remove epel-release on RHEL family; other system packages may
    # depend on it.
    pkgs_to_remove = [p for p in pkgs if p != "epel-release"]
    return {
        "platform": "linux",
        "av_product": "clamav",
        "files": [],
        "commands": [],
        "packages_to_remove": pkgs_to_remove,
        "service_actions": [
            {"service": clamd_svc, "action": "stop"},
            {"service": clamd_svc, "action": "disable"},
            {"service": fresh_svc, "action": "stop"},
            {"service": fresh_svc, "action": "disable"},
        ],
    }


def _bsd_deploy(
    host_info: Dict[str, Any],
    antivirus_package: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """BSD/macOS deploy plan with optional cadence + scan_schedule."""
    options = options or {}
    plat = (host_info.get("platform") or "").lower()
    pkg_mgr, clamd_conf, fresh_conf, clamd_svc, fresh_svc = _bsd_clamav_layout(plat)
    pkg_name = antivirus_package or "clamav"

    files: List[Dict[str, Any]] = [
        {
            "path": clamd_conf,
            "content": _basic_clamd_conf(),
            "mode": 0o644,
            "owner": "root",
            "group": "wheel",
            "backup": True,
        },
        {
            "path": fresh_conf,
            "content": _basic_freshclam_conf(options.get("checks_per_day")),
            "mode": 0o644,
            "owner": "root",
            "group": "wheel",
            "backup": True,
        },
    ]

    schedule = _validate_scan_schedule(options.get("scan_schedule"))
    if schedule:
        # BSD/macOS: drop a per-host crontab fragment under /etc/cron.d
        # on FreeBSD/Linux-style; OpenBSD/NetBSD use /etc/daily.local etc.
        # We pick /etc/cron.d for FreeBSD and /var/cron/tabs/root style for
        # the others. Keep it simple: use /etc/cron.d/sysmanage-clamscan on
        # FreeBSD, otherwise document the cron file via `note`.
        scan_cmd = _scan_command_for_paths(schedule["scan_paths"])
        cron_line = _cron_line_for_schedule(schedule, scan_cmd)
        if plat == "freebsd":
            files.append(
                {
                    "path": "/etc/cron.d/sysmanage-clamscan",
                    "content": (
                        "# Managed by sysmanage av_plan_builder — DO NOT EDIT\n"
                        "SHELL=/bin/sh\n"
                        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
                        f"{cron_line}\n"
                    ),
                    "mode": 0o644,
                    "owner": "root",
                    "group": "wheel",
                    "backup": True,
                }
            )

    return {
        "platform": plat,
        "av_product": "clamav",
        "packages": [{"manager": pkg_mgr, "name": pkg_name}],
        "files": files,
        "commands": [
            {
                "argv": ["freshclam"],
                "sudo": True,
                "timeout": 300,
                "ignore_errors": True,
                "description": "refresh ClamAV signature database",
            },
        ],
        "service_actions": [
            {"service": fresh_svc, "action": "enable"},
            {"service": fresh_svc, "action": "start"},
            {"service": clamd_svc, "action": "enable"},
            {"service": clamd_svc, "action": "start"},
        ],
        "scan_schedule": schedule or None,
    }


def _bsd_enable(host_info: Dict[str, Any]) -> Dict[str, Any]:
    plat = (host_info.get("platform") or "").lower()
    _, _, _, clamd_svc, fresh_svc = _bsd_clamav_layout(plat)
    return {
        "platform": plat,
        "av_product": "clamav",
        "files": [],
        "commands": [],
        "service_actions": [
            {"service": fresh_svc, "action": "enable"},
            {"service": fresh_svc, "action": "start"},
            {"service": clamd_svc, "action": "enable"},
            {"service": clamd_svc, "action": "start"},
        ],
    }


def _bsd_remove(host_info: Dict[str, Any]) -> Dict[str, Any]:
    plat = (host_info.get("platform") or "").lower()
    pkg_mgr, _, _, clamd_svc, fresh_svc = _bsd_clamav_layout(plat)
    return {
        "platform": plat,
        "av_product": "clamav",
        "files": [],
        "commands": [],
        "packages_to_remove": [{"manager": pkg_mgr, "name": "clamav"}],
        "service_actions": [
            {"service": clamd_svc, "action": "stop"},
            {"service": clamd_svc, "action": "disable"},
            {"service": fresh_svc, "action": "stop"},
            {"service": fresh_svc, "action": "disable"},
        ],
    }


def _windows_deploy(
    _host_info: Dict[str, Any],
    antivirus_package: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Windows ClamWin deploy plan with optional scan_schedule via schtasks."""
    options = options or {}
    pkg_name = antivirus_package or "clamwin"
    install_dir = r"C:\Program Files (x86)\ClamWin"

    # Pass checks_per_day through to the WarnOutdated stanza? ClamWin doesn't
    # have an exact equivalent; we just use the default 30-day warn threshold.
    commands: List[Dict[str, Any]] = [
        {
            "argv": [install_dir + r"\bin\freshclam.exe"],
            "sudo": False,
            "elevated": True,
            "timeout": 600,
            "ignore_errors": True,
            "description": "refresh ClamWin signature database",
        },
    ]

    schedule = _validate_scan_schedule(options.get("scan_schedule"))
    if schedule:
        # Build a `schtasks /Create` command for the scan.
        scan_paths = " ".join(f'"{p}"' for p in schedule["scan_paths"])
        scan_cmd = f'"{install_dir}\\bin\\clamscan.exe" -r {scan_paths}'
        if schedule["frequency"] == "daily":
            sc, modifier = "DAILY", []
        elif schedule["frequency"] == "weekly":
            day_map = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
            sc = "WEEKLY"
            modifier = ["/D", day_map[schedule["day_of_week"]]]
        else:  # monthly
            sc = "MONTHLY"
            modifier = ["/D", str(schedule["day_of_month"])]
        time_str = f"{schedule['hour']:02d}:{schedule['minute']:02d}"
        commands.append(
            {
                "argv": [
                    "schtasks",
                    "/Create",
                    "/TN",
                    "SysManage ClamWin Scan",
                    "/SC",
                    sc,
                    *modifier,
                    "/ST",
                    time_str,
                    "/TR",
                    scan_cmd,
                    "/F",
                ],
                "sudo": False,
                "elevated": True,
                "timeout": 30,
                "ignore_errors": True,
                "description": "register ClamWin scheduled scan",
            }
        )

    return {
        "platform": "windows",
        "av_product": "clamwin",
        "packages": [{"manager": "chocolatey", "name": pkg_name, "args": ["-y"]}],
        "files": [
            {
                "path": install_dir + r"\bin\ClamWin.conf",
                "content": (
                    "# ClamWin.conf - managed by sysmanage open-source AV planner\r\n"
                    "[ClamAV]\r\n"
                    f"Database = {install_dir}\\db\r\n"
                    "MaxFileSize = 20\r\n"
                    "ScanArchives = 1\r\n"
                    "[Updates]\r\n"
                    "Enable = 1\r\n"
                    "DBMirror = database.clamav.net\r\n"
                    "WarnOutdated = 30\r\n"
                ),
                "mode": 0o644,
                "encoding": "utf-8",
                "backup": True,
            },
        ],
        "commands": commands,
        "service_actions": [],
        "scan_schedule": schedule or None,
    }


def _windows_enable(_host_info: Dict[str, Any]) -> Dict[str, Any]:
    # ClamWin is on-demand, not service-based; "enable" just runs freshclam.
    install_dir = r"C:\Program Files (x86)\ClamWin"
    return {
        "platform": "windows",
        "av_product": "clamwin",
        "files": [],
        "commands": [
            {
                "argv": [install_dir + r"\bin\freshclam.exe"],
                "sudo": False,
                "elevated": True,
                "timeout": 600,
                "ignore_errors": True,
                "description": "refresh ClamWin signature database",
            },
        ],
        "service_actions": [],
    }


def _windows_remove(_host_info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "platform": "windows",
        "av_product": "clamwin",
        "files": [],
        "commands": [],
        "packages_to_remove": [
            {"manager": "chocolatey", "name": "clamwin", "args": ["-y"]}
        ],
        "service_actions": [],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _platform_kind(host_info: Dict[str, Any]) -> str:
    plat = (host_info.get("platform") or "").lower()
    if plat == "linux":
        return "linux"
    if plat in ("freebsd", "openbsd", "netbsd", "darwin", "macos"):
        return "bsd"
    if plat == "windows":
        return "windows"
    return "linux"


def build_deploy_plan(
    host_info: Dict[str, Any],
    antivirus_package: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a plan that installs and starts the OS-default antivirus.

    `options` may carry:
        checks_per_day (int 1-50): freshclam definition-update cadence
                                   per day (default 24 = hourly)
        scan_schedule (dict):      see _validate_scan_schedule. When set
                                   the plan adds an /etc/cron.d entry
                                   (Linux/FreeBSD) or a schtasks entry
                                   (Windows) for periodic clamdscan runs.
    """
    kind = _platform_kind(host_info)
    if kind == "linux":
        return _linux_deploy(host_info, antivirus_package, options)
    if kind == "windows":
        return _windows_deploy(host_info, antivirus_package, options)
    return _bsd_deploy(host_info, antivirus_package, options)


def build_enable_plan(host_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a plan that starts/enables the AV services on a host that already has it installed."""
    kind = _platform_kind(host_info)
    if kind == "linux":
        return _linux_enable(host_info)
    if kind == "windows":
        return _windows_enable(host_info)
    return _bsd_enable(host_info)


def build_remove_plan(host_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a plan that stops, disables, and uninstalls the AV product."""
    kind = _platform_kind(host_info)
    if kind == "linux":
        return _linux_remove(host_info)
    if kind == "windows":
        return _windows_remove(host_info)
    return _bsd_remove(host_info)


def build_disable_plan(host_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a plan that stops + disables the AV services without uninstalling."""
    kind = _platform_kind(host_info)
    if kind == "linux":
        distro = (host_info.get("platform_release") or "").lower()
        _, _, _, clamd_svc, fresh_svc = _linux_clamav_layout(distro)
        return {
            "platform": "linux",
            "av_product": "clamav",
            "files": [],
            "commands": [],
            "service_actions": [
                {"service": clamd_svc, "action": "stop"},
                {"service": clamd_svc, "action": "disable"},
                {"service": fresh_svc, "action": "stop"},
                {"service": fresh_svc, "action": "disable"},
            ],
        }
    if kind == "windows":
        # ClamWin has no daemon — disable is a no-op aside from removing
        # the scheduled update task if present.
        return {
            "platform": "windows",
            "av_product": "clamwin",
            "files": [],
            "commands": [
                {
                    "argv": [
                        "schtasks",
                        "/Delete",
                        "/TN",
                        "ClamWin Definition Update",
                        "/F",
                    ],
                    "sudo": False,
                    "elevated": True,
                    "timeout": 30,
                    "ignore_errors": True,
                    "description": "remove daily definition update task",
                },
            ],
            "service_actions": [],
        }
    plat = (host_info.get("platform") or "").lower()
    _, _, _, clamd_svc, fresh_svc = _bsd_clamav_layout(plat)
    return {
        "platform": plat,
        "av_product": "clamav",
        "files": [],
        "commands": [],
        "service_actions": [
            {"service": clamd_svc, "action": "stop"},
            {"service": clamd_svc, "action": "disable"},
            {"service": fresh_svc, "action": "stop"},
            {"service": fresh_svc, "action": "disable"},
        ],
    }
