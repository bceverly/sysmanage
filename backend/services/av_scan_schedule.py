# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Scheduled antivirus scans: validate a scan schedule, spread it per host,
render it as a cron line (split out of ``av_plan_builder``, which imports
these back under the same names)."""

from typing import Any, Dict, List, Optional

from backend.utils.host_spread import host_offset

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


# Phase 22.3: every host on one policy scanned at the same minute (03:00 by
# default) -- on shared storage or a virtualization host, the whole fleet's
# disks at once.  Each host's scan moves later by a fixed share of this
# window, from its id (stable: the same host always gets the same time), and
# never past 23:59, so a weekly or monthly scan keeps its day.
SCAN_SPLAY_MINUTES = 60


def _splay_schedule(
    schedule: Dict[str, Any], host_info: Dict[str, Any]
) -> Dict[str, Any]:
    """``schedule`` shifted by this host's share of SCAN_SPLAY_MINUTES; the
    shift is recorded as ``splay_minutes`` so the plan shows the real time."""
    host_id = (host_info or {}).get("host_id")
    if not schedule or not host_id:
        return schedule
    start = schedule["hour"] * 60 + schedule["minute"]
    shift = min(int(host_offset(host_id) * SCAN_SPLAY_MINUTES), 23 * 60 + 59 - start)
    total = start + shift
    return {
        **schedule,
        "hour": total // 60,
        "minute": total % 60,
        "splay_minutes": shift,
    }


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
