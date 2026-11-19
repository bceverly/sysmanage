# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Not safe to reboot (2026-11-19).

Production, 2026-11-19: an "update all" left three hosts with a
half-configured kernel and no initramfs, and "reboot required" -- one reboot
from booting a kernel that could not start.  With its package manager health
the agent now says whether a reboot would come back (agent
collection/boot_safety.py): a kernel, initramfs or boot loader package part-way
installed, or a kernel with no initramfs.

:func:`store` keeps that on the host.  Every reboot SysManage sends asks
:func:`reason` first: a person's reboot is refused with it (409), an
automatic one waits (``reboot_status`` "unsafe") and goes once the host is
safe again -- after "Repair package manager", or the host's next scan.  The
agent checks again itself before any reboot, whoever sent it, and finishes
part-way packages first.
"""

from typing import Any, Optional

from fastapi import HTTPException

from backend.i18n import _
from backend.persistence import models

REASON_MAX = 255


def store(host: Optional[models.Host], health: Any) -> bool:
    """Keep the agent's verdict; True when it changed.  An agent that says
    nothing about reboots (an older one) leaves the host as it was."""
    if host is None or not isinstance(health, dict) or "reboot_unsafe" not in health:
        return False
    before = bool(host.reboot_unsafe)
    unsafe = bool(health.get("reboot_unsafe"))
    why = health.get("reboot_unsafe_reason") if unsafe else None
    host.reboot_unsafe = unsafe
    host.reboot_unsafe_reason = (
        str(why)[:REASON_MAX] if isinstance(why, str) and why else None
    )
    return before != unsafe


def reason(host: Optional[models.Host]) -> Optional[str]:
    """Why ``host`` must not be rebooted now, or None."""
    # Only a stored True: anything else (an older row, a test double) is not
    # a verdict.
    if host is None or getattr(host, "reboot_unsafe", False) is not True:
        return None
    return host.reboot_unsafe_reason or _(
        "Not safe to reboot: the host may not boot. Repair the package manager first."
    )


def refuse_if_unsafe(host: Optional[models.Host]) -> None:
    """For a person's reboot: 409 with the reason."""
    why = reason(host)
    if why:
        raise HTTPException(status_code=409, detail=why)
