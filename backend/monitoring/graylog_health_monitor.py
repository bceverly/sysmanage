"""
Graylog health monitoring service for tracking integration status.
Periodically checks Graylog server health and detects available input ports.
"""

import asyncio
import logging
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

from backend.persistence.db import get_db
from backend.persistence.models import GraylogIntegrationSettings

logger = logging.getLogger(__name__)


async def check_graylog_health():  # NOSONAR
    """
    Check Graylog server health and detect available input ports.
    Updates the database with the results.
    """
    try:
        db = next(get_db())
    except Exception as e:
        logger.error("Failed to get database connection: %s", e)
        return

    try:
        # Get Graylog integration settings
        settings = db.query(GraylogIntegrationSettings).first()

        if not settings or not settings.enabled:
            # Graylog integration is not enabled, skip health check
            return

        # Get the Graylog URL
        graylog_url = settings.graylog_url
        if not graylog_url:
            logger.warning("Graylog integration enabled but no URL configured")
            return

        # Extract hostname from graylog_url
        parsed_url = urlparse(graylog_url)
        graylog_host = parsed_url.hostname or graylog_url.split("://")[-1].split(":")[0]

        logger.debug("Checking Graylog health for host: %s", graylog_host)

        # Detect available Graylog input ports
        # GELF TCP: typically 12201
        # Syslog TCP: typically 514 or 1514
        # Syslog UDP: typically 514 or 1514
        # Windows Sidecar (Beats): typically 5044

        has_gelf_tcp = False
        gelf_tcp_port = None
        has_syslog_tcp = False
        syslog_tcp_port = None
        has_syslog_udp = False
        syslog_udp_port = None
        has_windows_sidecar = False
        windows_sidecar_port = None

        # Check GELF TCP (12201)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((graylog_host, 12201))
            sock.close()
            if result == 0:
                has_gelf_tcp = True
                gelf_tcp_port = 12201
                logger.debug("GELF TCP port 12201 is open")
        except Exception as e:
            logger.debug("Error checking GELF TCP port: %s", e)

        # Check Syslog TCP (1514, then 514)
        for port in [1514, 514]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((graylog_host, port))
                sock.close()
                if result == 0:
                    has_syslog_tcp = True
                    syslog_tcp_port = port
                    logger.debug("Syslog TCP port %s is open", port)
                    break
            except Exception as e:
                logger.debug("Error checking Syslog TCP port %s: %s", port, e)

        # Check Syslog UDP (1514, then 514)
        # For UDP, we assume it's available if the TCP port is open on the same port
        for port in [1514, 514]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(2)
                # For UDP, we can't really "connect", so we just check if we can send
                # We'll assume it's available if the previous TCP check succeeded
                if has_syslog_tcp and syslog_tcp_port == port:
                    has_syslog_udp = True
                    syslog_udp_port = port
                    logger.debug("Syslog UDP port %s assumed available", port)
                sock.close()
                if has_syslog_udp:
                    break
            except Exception as e:
                logger.debug("Error checking Syslog UDP port %s: %s", port, e)

        # Check Windows Sidecar / Beats (5044)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((graylog_host, 5044))
            sock.close()
            if result == 0:
                has_windows_sidecar = True
                windows_sidecar_port = 5044
                logger.debug("Windows Sidecar port 5044 is open")
        except Exception as e:
            logger.debug("Error checking Windows Sidecar port: %s", e)

        # Update the database with detected ports
        settings.has_gelf_tcp = has_gelf_tcp
        settings.gelf_tcp_port = gelf_tcp_port
        settings.has_syslog_tcp = has_syslog_tcp
        settings.syslog_tcp_port = syslog_tcp_port
        settings.has_syslog_udp = has_syslog_udp
        settings.syslog_udp_port = syslog_udp_port
        settings.has_windows_sidecar = has_windows_sidecar
        settings.windows_sidecar_port = windows_sidecar_port
        settings.inputs_last_checked = datetime.now(timezone.utc)

        db.commit()
        logger.info(
            "Graylog health check completed - GELF TCP: %s, Syslog TCP: %s, Syslog UDP: %s, Windows Sidecar: %s",
            has_gelf_tcp,
            has_syslog_tcp,
            has_syslog_udp,
            has_windows_sidecar,
        )

    except Exception as e:
        logger.error("Error checking Graylog health: %s", e)
        db.rollback()
    finally:
        db.close()


async def graylog_health_monitor_service():
    """
    Background service that runs Graylog health checks every 5 minutes.
    """
    logger.info("Starting Graylog health monitor service")

    while True:
        try:
            await check_graylog_health()
            # Check every 5 minutes (300 seconds)
            await asyncio.sleep(300)
        except Exception as e:
            logger.error("Error in Graylog health monitor service: %s", e)
            # Wait a bit before retrying
            await asyncio.sleep(60)
