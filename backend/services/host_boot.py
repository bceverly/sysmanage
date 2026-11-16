# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""When a host last booted, from its heartbeat (ROADMAP 26.1).

An automatic update that reboots a host has to know whether the host came
back.  "The agent is heard from again" cannot tell a reboot from a reboot
that never happened (``shutdown -r +1`` leaves the agent running for a
minute, and a refused reboot leaves it running for good); a boot time later
than the reboot request can.
"""

from datetime import datetime, timezone


def note_boot_time(host, reported) -> None:
    """Store ``reported`` (ISO, from the agent) as naive UTC; ignore junk."""
    if not reported:
        return
    try:
        value = datetime.fromisoformat(str(reported))
    except ValueError:
        return
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    host.boot_time = value
