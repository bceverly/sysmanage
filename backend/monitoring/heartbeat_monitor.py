"""
Heartbeat monitoring service for tracking host status.
Periodically checks for hosts that haven't sent heartbeats and marks them as down.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from backend.config.config import get_heartbeat_timeout_minutes
from backend.persistence.db import get_db
from backend.persistence.models import Host

logger = logging.getLogger(__name__)


async def check_host_heartbeats():
    """
    Check for hosts that haven't sent heartbeats within the timeout period
    and mark them as down.
    """
    try:
        db = next(get_db())
    except Exception as e:
        logger.error("Failed to get database connection: %s", e)
        return

    try:
        timeout_minutes = get_heartbeat_timeout_minutes()
        # Use naive UTC time to match how last_access is stored (as naive UTC)
        timeout_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=timeout_minutes)

        # Find hosts that haven't been seen within the timeout period
        stale_hosts = (
            db.query(Host)
            .filter(Host.last_access < timeout_threshold)
            .filter(Host.status == "up")
            .all()
        )

        for host in stale_hosts:
            logger.info("Marking host %s as down due to heartbeat timeout", host.fqdn)
            host.status = "down"
            host.active = False

        if stale_hosts:
            db.commit()
            logger.info("Marked %s hosts as down", len(stale_hosts))

    except Exception as e:
        logger.error("Error checking host heartbeats: %s", e)
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
            logger.error("Error in heartbeat monitor service: %s", e)
            # Wait a bit before retrying
            await asyncio.sleep(30)
