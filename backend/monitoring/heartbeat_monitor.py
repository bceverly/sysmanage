# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Heartbeat monitoring service for tracking host status.
Periodically checks for hosts that haven't sent heartbeats and marks them as down.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from backend.config.config import get_heartbeat_timeout_minutes
from backend.persistence.models import Host
from backend.persistence.partitions import iter_host_databases

logger = logging.getLogger(__name__)


def _mark_stale_hosts_down(db, timeout_threshold, label):
    """Mark approved hosts in ``db`` that missed the heartbeat window as down.

    Only approved hosts are marked — pending hosts are expected to have comms
    gaps while awaiting approval."""
    stale_hosts = (
        db.query(Host)
        .filter(Host.last_access < timeout_threshold)
        .filter(Host.status == "up")
        .filter(Host.approval_status == "approved")
        .all()
    )
    for host in stale_hosts:
        logger.info(
            "Marking host %s as down due to heartbeat timeout (%s)", host.fqdn, label
        )
        host.status = "down"
        host.active = False
    if stale_hosts:
        db.commit()
        logger.info("Marked %s hosts as down (%s)", len(stale_hosts), label)


async def check_host_heartbeats():  # NOSONAR
    """Mark approved hosts that missed the heartbeat window as down, across the
    bootstrap DB and every provisioned tenant DB.  Each database is handled
    independently so one failure can't stall the rest."""
    for label, _, db in iter_host_databases():
        try:
            timeout_minutes = get_heartbeat_timeout_minutes()
            # Naive UTC to match how last_access is stored.
            timeout_threshold = datetime.now(timezone.utc).replace(
                tzinfo=None
            ) - timedelta(minutes=timeout_minutes)
            _mark_stale_hosts_down(db, timeout_threshold, label)
        except Exception as e:  # noqa: BLE001
            logger.exception("Error checking host heartbeats (%s): %s", label, e)
            db.rollback()
        finally:
            db.close()


async def heartbeat_monitor_service():
    """
    Background service that runs heartbeat checks every minute.
    """
    logger.info("Starting heartbeat monitor service")

    while True:
        try:
            await check_host_heartbeats()
            # Check every minute
            await asyncio.sleep(60)
        except Exception as e:
            logger.exception("Error in heartbeat monitor service: %s", e)
            # Wait a bit before retrying
            await asyncio.sleep(30)
