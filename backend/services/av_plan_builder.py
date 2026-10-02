# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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

# Bump whenever what a deploy plan writes changes: with malware detection
# licensed, av_auto_deploy re-pushes the plan to every equipped host whose
# recorded version is older.  2 = 2026-09-30 (no Linux paths on the BSDs,
# macOS launchd freshclam, Windows update cadence).  3 = 2026-09-30 (agent's
# package-manager names "pkg"/"choco"; Windows = official ClamAV, not ClamWin).
# 4 = 2026-09-30 (Windows via winget Cisco.ClamAV: Chocolatey's "clamav" is
# the portable zip, unpacked under a versioned lib folder, never Program Files).
# 5 = 2026-09-30 (FreeBSD clamd.conf PidFile: the rc script decides "running"
# from it, so clamd ran unseen -- status "not running", and stop impossible).
# 6 = 2026-10-01 (wait for that clamd to EXIT before starting it: the start
# raced its shutdown, rc said "already running", and none was left; syslog
# facility LOG_DAEMON so ClamAV's messages land somewhere).
PLAN_VERSION = 6

# ---------------------------------------------------------------------------
# Conf-file paths used by multiple distro layouts (deduped to satisfy
# Sonar's duplicate-string-literal rule).
# ---------------------------------------------------------------------------

CLAMD_CONF_DEBIAN = "/etc/clamav/clamd.conf"
FRESHCLAM_CONF_DEBIAN = "/etc/clamav/freshclam.conf"
FRESHCLAM_CONF_RPM = "/etc/freshclam.conf"
REFRESH_SIGNATURES = "refresh ClamAV signature database"

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


# Package-specific runtime facts, read from each platform's own ClamAV
# package (FreeBSD port security/clamav, OpenBSD ports, pkgsrc, Homebrew),
# 2026-09-30: (clamd user, directory for clamd's socket).  The socket lives
# where the package guarantees a directory exists: FreeBSD's rc script
# creates /var/run/clamav; OpenBSD clears /var/run at boot, so there -- and
# on NetBSD -- it goes in the package's own database directory.
_BSD_RUNTIME = {
    "freebsd": ("clamav", "/var/run/clamav"),
    "openbsd": ("_clamav", "/var/db/clamav"),
    "netbsd": ("clamav", "/var/clamav"),
}


def _brew_prefix(host_info: Optional[Dict[str, Any]]) -> str:
    """Homebrew lives in /opt/homebrew on Apple silicon, /usr/local on Intel."""
    arch = ((host_info or {}).get("machine_architecture") or "").lower()
    return "/opt/homebrew" if arch in ("arm64", "aarch64") else "/usr/local"


def _bsd_clamav_layout(
    plat: str, host_info: Optional[Dict[str, Any]] = None
) -> Tuple[str, str, str, str, str]:
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
        # The agent's installer is named for pkg(8) and runs pkg_add on OpenBSD.
        return (
            "pkg",
            "/etc/clamd.conf",
            "/etc/freshclam.conf",
            "clamd",
            "freshclam",
        )
    if p == "netbsd":
        # pkgsrc installs the updater's rc.d script as "freshclamd".
        return (
            "pkgin",
            "/usr/pkg/etc/clamd.conf",
            "/usr/pkg/etc/freshclam.conf",
            "clamd",
            "freshclamd",
        )
    # darwin / macos: Homebrew ships no freshclam service; the plan installs
    # a launchd job for it (see _macos_freshclam_job).
    prefix = _brew_prefix(host_info)
    return (
        "brew",
        f"{prefix}/etc/clamav/clamd.conf",
        f"{prefix}/etc/clamav/freshclam.conf",
        "clamav",
        MACOS_FRESHCLAM_LABEL,
    )


MACOS_FRESHCLAM_LABEL = "org.sysmanage.freshclam"
MACOS_FRESHCLAM_PLIST = f"/Library/LaunchDaemons/{MACOS_FRESHCLAM_LABEL}.plist"


def _macos_freshclam_job(prefix: str) -> str:
    """launchd job running freshclam as a daemon: it wakes ``Checks`` times a
    day on its own, and launchd restarts it if it dies."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        f"  <key>Label</key><string>{MACOS_FRESHCLAM_LABEL}</string>\n"
        "  <key>ProgramArguments</key><array>\n"
        f"    <string>{prefix}/bin/freshclam</string>\n"
        "    <string>--daemon</string><string>--foreground</string>\n"
        "  </array>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "  <key>KeepAlive</key><true/>\n"
        "</dict></plist>\n"
    )


FREEBSD_CLAMD_PIDFILE = "/var/run/clamav/clamd.pid"


def _freebsd_stop_unseen_clamd() -> Dict[str, Any]:
    """A clamd started without PidFile is invisible to rc ("not running"), so
    rc can neither stop it nor start another (its socket is live).  Ending
    it here lets the service actions start it under the new config -- which
    a redeploy needs anyway, since "start" leaves a running clamd on the old
    one."""
    return {
        # pkill only signals: wait (at most 30 s) for the old clamd to EXIT,
        # or the start that follows sees its pid file, says "already running",
        # and nothing is left once it finishes dying (FreeBSD, 2026-09-30).
        "argv": [
            "/bin/sh",
            "-c",
            (
                "pkill -x clamd; i=0; "
                "while pgrep -x clamd >/dev/null && [ $i -lt 30 ]; "
                "do sleep 1; i=$((i+1)); done; true"
            ),
        ],
        "sudo": True,
        "timeout": 60,
        "ignore_errors": True,
        "description": "restart clamd under the deployed configuration",
    }


def _bsd_clamd_conf(plat: str, host_info: Optional[Dict[str, Any]]) -> str:
    """clamd.conf for the BSDs and macOS: the package's own user, a socket in
    a directory the package guarantees, syslog instead of a log file whose
    directory may not exist.  No DatabaseDirectory: clamd's compiled default
    is where freshclam puts the database."""
    user, sock_dir = _BSD_RUNTIME.get(plat, (None, None))
    if sock_dir is None:  # macOS / Homebrew: runs as root under launchd
        sock_dir = f"{_brew_prefix(host_info)}/var/lib/clamav"
    lines = [
        "# clamd.conf - managed by sysmanage open-source AV planner",
        "# DO NOT EDIT MANUALLY - overwrites on every deploy",
        "",
        "LogSyslog yes",
        # ClamAV's default facility is LOCAL6, which stock syslog configs
        # (FreeBSD's included) route nowhere: its messages were simply lost.
        "LogFacility LOG_DAEMON",
        f"LocalSocket {sock_dir}/clamd.sock",
        "FixStaleSocket yes",
        "ScanArchive yes",
        "MaxFileSize 100M",
        "MaxScanSize 400M",
    ]
    if user:
        lines.insert(3, f"User {user}")
    if plat == "freebsd":
        # The port's rc script reads this path to decide whether clamd runs;
        # clamd writes no pid file unless told to.
        lines.append(f"PidFile {FREEBSD_CLAMD_PIDFILE}")
    return "\n".join(lines) + "\n"


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
    )


DEFAULT_CHECKS_PER_DAY = 12
MAX_CHECKS_PER_DAY = 24


def clamp_checks(value: Any) -> int:
    """freshclam's daily update checks: default 12 (every two hours), at most
    24 (hourly).  ClamAV's mirrors throttle clients that download too often
    (HTTP 429), so anything above hourly is clamped, never passed through."""
    cadence = value if isinstance(value, int) else DEFAULT_CHECKS_PER_DAY
    return min(max(cadence, 1), MAX_CHECKS_PER_DAY)


def _basic_freshclam_conf(
    checks_per_day: Optional[int] = None, database_owner: Optional[str] = None
) -> str:
    """
    Render freshclam.conf with a configurable definition-update cadence.

    DatabaseDirectory and DatabaseOwner are deliberately NOT set: every
    package compiles in its own (Debian /var/lib/clamav + clamav, RHEL
    clamupdate, FreeBSD/OpenBSD /var/db/clamav, OpenBSD _clamav, NetBSD
    /var/clamav), and clamscan reads the SAME compiled default -- so the
    database always lands where the scanner looks.  Hard-coding
    /var/lib/clamav + clamav (as this did before 2026-09-30) put the BSDs'
    signatures where clamscan never looked and failed outright on OpenBSD.
    ``database_owner`` is only for macOS, whose Homebrew build defaults to a
    ``clamav`` user that does not exist there.
    """
    lines = [
        "# freshclam.conf - managed by sysmanage open-source AV planner",
        "# DO NOT EDIT MANUALLY - overwrites on every deploy",
        "",
        "LogSyslog yes",
        # ClamAV's default facility is LOCAL6, which stock syslog configs
        # (FreeBSD's included) route nowhere: its messages were simply lost.
        "LogFacility LOG_DAEMON",
        "DatabaseMirror database.clamav.net",
        f"Checks {clamp_checks(checks_per_day)}",
    ]
    if database_owner:
        lines.append(f"DatabaseOwner {database_owner}")
    return "\n".join(lines) + "\n"


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
    daemon, falling back to `clamscan` (slower) is the operator's call --
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
        checks_per_day: int (1-24) -- freshclam definition-update cadence
        scan_schedule:  dict -- see _validate_scan_schedule. When set, an
                       /etc/cron.d/sysmanage-clamscan file is added to
                       the plan with a cron entry that invokes clamdscan
                       on the configured paths and frequency.
    """
    options = options or {}
    distro = (host_info.get("platform_release") or "").lower()
    pkgs, clamd_conf, fresh_conf, clamd_svc, fresh_svc = _linux_clamav_layout(distro)
    if antivirus_package and antivirus_package not in pkgs:
        # Caller's choice of package wins -- the OS defaults table may
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
                    "# Managed by sysmanage av_plan_builder -- DO NOT EDIT\n"
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
                "description": REFRESH_SIGNATURES,
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
    pkg_mgr, clamd_conf, fresh_conf, clamd_svc, fresh_svc = _bsd_clamav_layout(
        plat, host_info
    )
    pkg_name = antivirus_package or "clamav"
    macos = plat in ("darwin", "macos")

    files: List[Dict[str, Any]] = [
        {
            "path": clamd_conf,
            "content": _bsd_clamd_conf(plat, host_info),
            "mode": 0o644,
            "owner": "root",
            "group": "wheel",
            "backup": True,
        },
        {
            "path": fresh_conf,
            "content": _basic_freshclam_conf(
                options.get("checks_per_day"), "root" if macos else None
            ),
            "mode": 0o644,
            "owner": "root",
            "group": "wheel",
            "backup": True,
        },
    ]
    if macos:
        files.append(
            {
                "path": MACOS_FRESHCLAM_PLIST,
                "content": _macos_freshclam_job(_brew_prefix(host_info)),
                "mode": 0o644,
                "owner": "root",
                "group": "wheel",
                "backup": True,
            }
        )

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
                        "# Managed by sysmanage av_plan_builder -- DO NOT EDIT\n"
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
        "commands": _bsd_update_commands(plat, host_info),
        "service_actions": _bsd_service_actions(plat, clamd_svc, fresh_svc),
        "scan_schedule": schedule or None,
    }


def _bsd_update_commands(plat: str, host_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Refresh the database now, and on macOS load the freshclam launchd job
    (Homebrew has no freshclam service to enable)."""
    if plat not in ("darwin", "macos"):
        commands = [
            {
                "argv": ["freshclam"],
                "sudo": True,
                "timeout": 300,
                "ignore_errors": True,
                "description": REFRESH_SIGNATURES,
            },
        ]
        if plat == "freebsd":
            commands.append(_freebsd_stop_unseen_clamd())
        return commands
    prefix = _brew_prefix(host_info)
    return [
        {
            "argv": [f"{prefix}/bin/freshclam"],
            "sudo": True,
            "timeout": 300,
            "ignore_errors": True,
            "description": REFRESH_SIGNATURES,
        },
        {
            "argv": ["launchctl", "bootstrap", "system", MACOS_FRESHCLAM_PLIST],
            "sudo": True,
            "timeout": 30,
            # Already loaded on a re-deploy: launchctl says so and exits 5.
            "ignore_errors": True,
            "description": "schedule ClamAV signature updates (launchd)",
        },
    ]


def _bsd_service_actions(plat: str, clamd_svc: str, fresh_svc: str) -> list:
    if plat in ("darwin", "macos"):
        # freshclam runs from its own launchd job; clamd is optional (a
        # malware scan falls back to a one-shot clamscan when there is memory).
        return []
    return [
        {"service": fresh_svc, "action": "enable"},
        {"service": fresh_svc, "action": "start"},
        {"service": clamd_svc, "action": "enable"},
        {"service": clamd_svc, "action": "start"},
    ]


def _bsd_enable(host_info: Dict[str, Any]) -> Dict[str, Any]:
    plat = (host_info.get("platform") or "").lower()
    _, _, _, clamd_svc, fresh_svc = _bsd_clamav_layout(plat, host_info)
    macos = plat in ("darwin", "macos")
    return {
        "platform": plat,
        "av_product": "clamav",
        "files": [],
        "commands": _bsd_update_commands(plat, host_info) if macos else [],
        "service_actions": _bsd_service_actions(plat, clamd_svc, fresh_svc),
    }


def _macos_unload_job() -> List[Dict[str, Any]]:
    return [
        {
            "argv": ["launchctl", "bootout", f"system/{MACOS_FRESHCLAM_LABEL}"],
            "sudo": True,
            "timeout": 30,
            "ignore_errors": True,
            "description": "stop scheduled ClamAV signature updates (launchd)",
        },
    ]


def _bsd_remove(host_info: Dict[str, Any]) -> Dict[str, Any]:
    plat = (host_info.get("platform") or "").lower()
    pkg_mgr, _, _, clamd_svc, fresh_svc = _bsd_clamav_layout(plat, host_info)
    return {
        "platform": plat,
        "av_product": "clamav",
        "files": [],
        "commands": _macos_unload_job() if plat in ("darwin", "macos") else [],
        "packages_to_remove": [{"manager": pkg_mgr, "name": "clamav"}],
        "service_actions": [
            {"service": clamd_svc, "action": "stop"},
            {"service": clamd_svc, "action": "disable"},
            {"service": fresh_svc, "action": "stop"},
            {"service": fresh_svc, "action": "disable"},
        ],
    }


# Windows runs the official ClamAV MSI (winget ``Cisco.ClamAV``, native arm64
# too), not ClamWin and not Chocolatey's ``clamav`` -- that one is the portable
# zip, unpacked to chocolatey\lib\clamav\tools\clamav-<version>.win.x64, so
# nothing ever reached the directory below (found on x13s, 2026-09-30):
# ClamWin's newest release is ClamAV 0.103 (end of life), and both the agent's
# antivirus detection and its malware scanner look in C:\Program Files\ClamAV
# -- a ClamWin install was never detected, so it could never be scanned with.
WINDOWS_INSTALL_DIR = r"C:\Program Files\ClamAV"
WINDOWS_PACKAGE = "Cisco.ClamAV"
WINDOWS_UPDATE_TASK = "SysManage ClamAV Update"
WINDOWS_SCAN_TASK = "SysManage ClamAV Scan"


def _windows_package(antivirus_package: str) -> str:
    """The winget package id: the product names ``clamav``/``clamwin`` (the
    seeded defaults) mean official ClamAV (see above); anything else is an
    operator's own winget id."""
    pkg = (antivirus_package or "").strip()
    return WINDOWS_PACKAGE if pkg.lower() in ("", "clamwin", "clamav") else pkg


def _windows_freshclam_conf(checks: Optional[int]) -> str:
    # No DatabaseDirectory: freshclam and clamscan share the build's default
    # (<install dir>\database), as on every other platform.
    return (
        "# freshclam.conf - managed by sysmanage open-source AV planner\r\n"
        "# DO NOT EDIT MANUALLY - overwrites on every deploy\r\n"
        "DatabaseMirror database.clamav.net\r\n"
        f"Checks {clamp_checks(checks)}\r\n"
    )


def _windows_database_dir_command() -> Dict[str, Any]:
    """freshclam refuses to run when its database directory is missing, and
    the package does not promise to create it."""
    path = WINDOWS_INSTALL_DIR + r"\database"
    return {
        "argv": [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            f"New-Item -ItemType Directory -Force -Path '{path}' | Out-Null",
        ],
        "sudo": False,
        "elevated": True,
        "timeout": 60,
        "ignore_errors": True,
        "description": "create the ClamAV database directory",
    }  # fmt: skip


def _windows_refresh_command() -> Dict[str, Any]:
    return {
        "argv": [WINDOWS_INSTALL_DIR + r"\freshclam.exe"],
        "sudo": False,
        "elevated": True,
        "timeout": 600,
        "ignore_errors": True,
        "description": REFRESH_SIGNATURES,
    }


def _windows_scan_task(schedule: Dict[str, Any]) -> Dict[str, Any]:
    scan_paths = " ".join(f'"{p}"' for p in schedule["scan_paths"])
    scan_cmd = f'"{WINDOWS_INSTALL_DIR}\\clamscan.exe" -r {scan_paths}'
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
    return {
        "argv": [
            "schtasks", "/Create", "/TN", WINDOWS_SCAN_TASK, "/SC", sc, *modifier,
            "/ST", time_str, "/TR", scan_cmd, "/RU", "SYSTEM", "/F",
        ],
        "sudo": False,
        "elevated": True,
        "timeout": 30,
        "ignore_errors": True,
        "description": "register ClamAV scheduled scan",
    }  # fmt: skip


def _windows_deploy(
    _host_info: Dict[str, Any],
    antivirus_package: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Windows ClamAV deploy plan with optional scan_schedule via schtasks."""
    options = options or {}
    checks = options.get("checks_per_day")
    commands: List[Dict[str, Any]] = [
        _windows_database_dir_command(),
        _windows_refresh_command(),
        _windows_update_task(WINDOWS_INSTALL_DIR, checks),
    ]
    schedule = _validate_scan_schedule(options.get("scan_schedule"))
    if schedule:
        commands.append(_windows_scan_task(schedule))
    return {
        "platform": "windows",
        "av_product": "clamav",
        "packages": [
            {"manager": "winget", "name": _windows_package(antivirus_package)}
        ],
        "files": [
            {
                "path": WINDOWS_INSTALL_DIR + r"\freshclam.conf",
                "content": _windows_freshclam_conf(checks),
                "mode": 0o644,
                "encoding": "utf-8",
                "backup": True,
            },
        ],
        "commands": commands,
        "service_actions": [],
        "scan_schedule": schedule or None,
    }


def _windows_update_task(install_dir: str, checks: Optional[int]) -> Dict[str, Any]:
    """A scheduled task running freshclam every 24 / checks hours as SYSTEM.
    Windows has no freshclam service, and a one-off update at install time
    leaves the signatures to go stale.  The name matches what the disable
    plan deletes."""
    every = max(1, 24 // clamp_checks(checks))
    return {
        "argv": [
            "schtasks", "/Create", "/TN", WINDOWS_UPDATE_TASK,
            "/SC", "HOURLY", "/MO", str(every),
            "/TR", f'"{install_dir}\\freshclam.exe"',
            "/RU", "SYSTEM", "/F",
        ],
        "sudo": False,
        "elevated": True,
        "timeout": 30,
        "ignore_errors": False,
        "description": "schedule ClamAV signature updates",
    }  # fmt: skip


def _windows_delete_tasks() -> List[Dict[str, Any]]:
    return [
        {
            "argv": ["schtasks", "/Delete", "/TN", task, "/F"],
            "sudo": False,
            "elevated": True,
            "timeout": 30,
            "ignore_errors": True,
            "description": "remove scheduled ClamAV task",
        }
        for task in (WINDOWS_UPDATE_TASK, WINDOWS_SCAN_TASK)
    ]


def _windows_enable(_host_info: Dict[str, Any]) -> Dict[str, Any]:
    # ClamAV on Windows runs on demand; "enable" refreshes and reschedules.
    return {
        "platform": "windows",
        "av_product": "clamav",
        "files": [],
        "commands": [
            _windows_refresh_command(),
            _windows_update_task(WINDOWS_INSTALL_DIR, None),
        ],
        "service_actions": [],
    }


def _windows_disable() -> Dict[str, Any]:
    return {
        "platform": "windows",
        "av_product": "clamav",
        "files": [],
        "commands": _windows_delete_tasks(),
        "service_actions": [],
    }


def _windows_remove(_host_info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "platform": "windows",
        "av_product": "clamav",
        "files": [],
        "commands": _windows_delete_tasks(),
        "packages_to_remove": [{"manager": "winget", "name": WINDOWS_PACKAGE}],
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
        checks_per_day (int 1-24): freshclam definition-update cadence
                                   per day (default 12 = every two hours)
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
        return _windows_disable()
    plat = (host_info.get("platform") or "").lower()
    _, _, _, clamd_svc, fresh_svc = _bsd_clamav_layout(plat, host_info)
    return {
        "platform": plat,
        "av_product": "clamav",
        "files": [],
        "commands": _macos_unload_job() if plat in ("darwin", "macos") else [],
        "service_actions": [
            {"service": clamd_svc, "action": "stop"},
            {"service": clamd_svc, "action": "disable"},
            {"service": fresh_svc, "action": "stop"},
            {"service": fresh_svc, "action": "disable"},
        ],
    }
