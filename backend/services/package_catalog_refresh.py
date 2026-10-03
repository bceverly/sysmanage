# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ask every host to refresh its available-package catalog, daily.

WHY THIS EXISTS
---------------
Nothing refreshed the catalog on a schedule.  A host was asked for its packages
exactly once -- when it had no rows -- and then never again, so ``available_packages``
froze at whatever the machine happened to offer on the day it enrolled.  New
releases, security updates and repository changes never appeared.

That gap was invisible until recently because a bug was papering over it: a
field-comparison error rejected every Linux catalog, the "no rows for this OS"
trigger therefore fired forever, and the fleet re-sent its full ~89k-package
catalog roughly every 13 minutes.  It was expensive and wrong, but it did keep
the data fresh.  Fixing the loop removed the accidental refresh with it, which
is what this service replaces -- deliberately, and once a day.

PER HOST, NOT PER OS
--------------------
There is no canonical package list for an operating system.  Two Ubuntu 26.04
machines legitimately differ: one carries a PPA, another points at an internal
mirror, a third has universe disabled, a fourth is air-gapped behind a private
repository.  So this asks EVERY host for its OWN catalog rather than sampling
one machine and publishing its repositories as the OS's.

WHY A DAILY FULL SWEEP IS CHEAP
-------------------------------
Each request carries the fingerprint of the catalog the server already holds
for that specific host.  An unchanged host transmits NOTHING; a changed one
sends only puts and takes.  A full catalog crosses the wire only when the two
sides genuinely disagree about the base -- so the steady-state cost of a daily
sweep is roughly one small message per host, not ~11 MB per host.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from backend.startup.tick_runner import run_periodic
from backend.utils.host_spread import host_offset

logger = logging.getLogger(__name__)

# Each host is still asked about once a day -- the agent re-scans its own
# package managers on that cadence -- but the PASS runs hourly (Phase 22.3):
# one daily pass asked every stale host at the same moment, and the whole
# fleet then scanned and answered together.
DEFAULT_INTERVAL_SECONDS = 3600

# How stale a host's catalog must be before it is re-requested: 20 hours plus
# this host's fixed share of SPREAD_HOURS, so the fleet's requests spread over
# the hourly passes instead of all falling due in one.
STALE_AFTER_HOURS = 20
SPREAD_HOURS = 4

# At most this many requests per database per pass: a fleet that enrolled
# together (no catalog yet, all due at once) is asked over several passes.
MAX_ASKS_PER_PASS = 500

# Back-off after a whole-pass failure: shorter than the cadence so an operator
# sees recovery, but not so short it spams the log on a persistent fault.
ERROR_BACKOFF_SECONDS = 300


def _needs_refresh(host, now: datetime) -> bool:
    """Has this host's catalog gone stale (or never arrived)?

    A host with no recorded fingerprint has never successfully delivered one,
    so it is always asked -- that is the case where the data is most obviously
    missing rather than merely old.
    """
    if not getattr(host, "available_packages_fingerprint", None):
        return True
    reported = getattr(host, "available_packages_fingerprint_at", None)
    if reported is None:
        return True
    if reported.tzinfo is None:
        reported = reported.replace(tzinfo=timezone.utc)
    stale_after = STALE_AFTER_HOURS + SPREAD_HOURS * host_offset(host.id)
    return now - reported >= timedelta(hours=stale_after)


def request_refresh_for_stale_hosts(session, models, now: datetime) -> int:
    """Queue a catalog request for every stale host in ONE database.

    Returns how many hosts were asked.  Never raises for a single host: one
    unqueueable message must not stop the rest of the fleet being refreshed.
    """
    # Late imports: avoid an import cycle at module import time, matching the
    # other background services.
    from backend.websocket.messages import create_command_message  # noqa: PLC0415
    from backend.websocket.queue_enums import Priority, QueueDirection  # noqa: PLC0415
    from backend.websocket.queue_manager import server_queue_manager  # noqa: PLC0415

    hosts = (
        session.query(models.Host)
        .filter(
            models.Host.active.is_(True),
            models.Host.approval_status == "approved",
        )
        .all()
    )

    asked = 0
    for host in hosts:
        if asked >= MAX_ASKS_PER_PASS:
            break  # the rest are still stale: a later pass asks them
        if not _needs_refresh(host, now):
            continue
        try:
            command = create_command_message(
                command_type="collect_available_packages",
                # The fingerprint is what makes a daily sweep affordable: an
                # unchanged host answers with nothing at all.
                parameters={"known_fingerprint": host.available_packages_fingerprint},
            )
            server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command,
                direction=QueueDirection.OUTBOUND,
                host_id=host.id,
                priority=Priority.LOW,
                db=session,
            )
            asked += 1
        except Exception:  # pylint: disable=broad-except
            # Loud, with the host, per the "log unresolvable edge cases" rule:
            # a host silently never refreshing is the failure this service
            # exists to end.
            logger.exception(
                "Could not queue a package-catalog refresh for host %s (%s)",
                getattr(host, "fqdn", "?"),
                getattr(host, "id", "?"),
            )
    return asked


def _run_one_pass() -> int:
    """Ask every stale host across all tenant databases.  Never raises."""
    from backend.persistence import models  # noqa: PLC0415
    from backend.persistence.partitions import iter_host_databases  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    total = 0
    for label, tenant_id, session in iter_host_databases():
        try:
            asked = request_refresh_for_stale_hosts(session, models, now)
            session.commit()
            total += asked
            if asked:
                logger.info(
                    "package-catalog refresh: asked %d host(s) in %s (tenant_id=%s)",
                    asked,
                    label,
                    tenant_id,
                )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "package-catalog refresh failed for %s (tenant_id=%s) -- "
                "continuing with the other databases",
                label,
                tenant_id,
            )
        finally:
            session.close()
    return total


async def run_package_catalog_refresh_loop(
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Background service: refresh every host's package catalog on a cadence.

    Cancellable via ``task.cancel()``; every other exception is caught so the
    loop is self-healing and never dies.
    """

    def _report(total):
        logger.info("package-catalog refresh pass complete: %d host(s) asked", total)

    await run_periodic(
        "Package-catalog refresh loop",
        _run_one_pass,
        interval_seconds,
        ERROR_BACKOFF_SECONDS,
        on_result=_report,
        logger=logger,
    )
