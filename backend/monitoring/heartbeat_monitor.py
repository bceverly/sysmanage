"""
Heartbeat monitoring service for tracking host status.
Periodically checks for hosts that haven't sent heartbeats and marks them as down.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from backend.config import config
from backend.config.config import get_heartbeat_timeout_minutes
from backend.persistence.db import get_db
from backend.persistence.models import Host, RegistryTenantPlacement
from backend.persistence.partitions import (
    PARTITION_REGISTRY,
    PARTITION_TENANT,
    partition_session,
    resolve_engine,
)

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


def _bootstrap_session():
    """A session on the bootstrap / main DB.  In its own (non-generator)
    function so ``next(get_db())`` can't leak ``StopIteration`` into the
    ``_host_databases`` generator (PEP 479)."""
    return next(get_db())


def _host_databases():
    """Yield ``(label, session)`` for the bootstrap DB and every provisioned
    tenant DB (Phase 13.1 — a bound host's row lives in its tenant database, so
    it must be checked there).  Single-tenant mode yields only the bootstrap DB,
    identical to the prior behaviour.  Mirrors the queue processor's fan-out."""
    try:
        bootstrap = _bootstrap_session()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to get bootstrap database connection")
        return
    yield ("bootstrap", bootstrap)

    if not config.is_multitenancy_enabled():
        return

    try:
        with partition_session(partition=PARTITION_REGISTRY) as session:
            rows = session.query(RegistryTenantPlacement.tenant_id).distinct().all()
        tenant_ids = [str(tenant_id) for (tenant_id,) in rows]
    except Exception:  # noqa: BLE001
        logger.error(
            "heartbeat: could not list provisioned tenants; checking the "
            "bootstrap DB only this cycle",
            exc_info=True,
        )
        return

    for tenant_id in tenant_ids:
        try:
            engine = resolve_engine(partition=PARTITION_TENANT, tenant_id=tenant_id)
        except Exception:  # noqa: BLE001
            logger.error(
                "heartbeat: could not resolve the engine for tenant %s; skipping "
                "its hosts this cycle",
                tenant_id,
                exc_info=True,
            )
            continue
        yield (f"tenant {tenant_id}", sessionmaker(bind=engine)())


async def check_host_heartbeats():  # NOSONAR
    """Mark approved hosts that missed the heartbeat window as down, across the
    bootstrap DB and every provisioned tenant DB.  Each database is handled
    independently so one failure can't stall the rest."""
    for label, db in _host_databases():
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
