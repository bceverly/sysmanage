"""
Background message processor for SysManage.
Processes queued messages from agents asynchronously.
"""

import asyncio

from sqlalchemy.orm import sessionmaker

from backend.config import config
from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import RegistryTenantPlacement
from backend.persistence.partitions import (
    PARTITION_REGISTRY,
    PARTITION_TENANT,
    partition_session,
    resolve_engine,
)
from backend.utils.verbosity_logger import get_logger
from backend.websocket.inbound_processor import process_pending_messages
from backend.websocket.outbound_processor import process_outbound_messages
from backend.websocket.queue_manager import server_queue_manager

logger = get_logger(__name__)


class MessageProcessor:
    """
    Background service that processes queued messages from agents.

    This service runs continuously, dequeuing messages and processing them
    using the appropriate handlers. It ensures reliable processing of
    agent data updates without blocking WebSocket connections.
    """

    def __init__(self):
        """Initialize the message processor."""
        self.running = False
        self.process_interval = 1.0  # Process messages every second

    async def start(self):
        """Start the background message processing loop."""
        # Use both logger and print to ensure we see the message
        logger.info("DEBUG: MessageProcessor.start() called")
        print("DEBUG: MessageProcessor.start() called", flush=True)

        if self.running:
            logger.info("DEBUG: MessageProcessor already running, returning early")
            print(
                "DEBUG: MessageProcessor already running, returning early", flush=True
            )
            return

        self.running = True
        logger.info(_("Message processor started"))
        print("DEBUG: Message processor started - running flag set to True", flush=True)

        cycle_count = 0
        try:
            while self.running:
                cycle_count += 1
                try:
                    print(
                        f"Processing cycle #{cycle_count} - About to call _process_pending_messages()",
                        flush=True,
                    )
                    logger.info("Processing cycle #%s starting", cycle_count)
                    await self._process_pending_messages()
                    print(
                        f"Processing cycle #{cycle_count} - Finished calling _process_pending_messages()",
                        flush=True,
                    )
                    logger.info("Processing cycle #%s completed", cycle_count)
                except Exception as e:
                    logger.exception(
                        _("Error in message processing loop: %s"), str(e), exc_info=True
                    )
                    print(
                        f"Error in processing cycle #{cycle_count}: {e}",
                        flush=True,
                    )

                # Wait before next processing cycle
                print(
                    f"Cycle #{cycle_count} complete - Sleeping for {self.process_interval} seconds before next cycle",
                    flush=True,
                )
                logger.info(
                    "Cycle #%s complete, sleeping %ss",
                    cycle_count,
                    self.process_interval,
                )
                await asyncio.sleep(self.process_interval)
        except asyncio.CancelledError:
            logger.info(_("Message processor cancelled"))
            raise
        finally:
            self.running = False
            logger.info(_("Message processor stopped"))

    def stop(self):
        """Stop the background message processing."""
        self.running = False

    async def _process_pending_messages(self):
        """Drain the message queue in the bootstrap DB and every provisioned
        tenant DB (Phase 13.1 #2 — per-tenant queues).

        Each database is drained INDEPENDENTLY: a failure on one is logged and
        isolated (rolled back) so it cannot stall the other tenants or the next
        cycle.  In collapsed/single-tenant mode this is exactly one pass over the
        bootstrap DB, identical to the prior behaviour.
        """
        for label, db in self._queue_sessions():
            try:
                # Inbound (agents→server), then outbound (server→agents).
                await process_pending_messages(db)
                await process_outbound_messages(db)

                # Retry messages that were sent but not acknowledged within the
                # timeout (websocket send succeeded but the agent disconnected
                # before processing).
                retry_count = server_queue_manager.retry_unacknowledged_messages(
                    timeout_seconds=60, db=db
                )
                if retry_count > 0:
                    logger.info(
                        "Scheduled %d unacknowledged messages for retry (%s)",
                        retry_count,
                        label,
                    )

                db.commit()
                logger.debug("Committed message processing changes (%s)", label)
            except (
                Exception
            ) as e:  # noqa: BLE001 — isolate per-DB; never stall the rest
                logger.exception(
                    "Error draining the %s message queue, rolling back: %s",
                    label,
                    str(e),
                )
                db.rollback()
            finally:
                db.close()

    @staticmethod
    def _bootstrap_session():
        """A session on the bootstrap / main application DB.

        In its own (non-generator) method so ``next(get_db())`` can't leak a
        ``StopIteration`` into the ``_queue_sessions`` generator (PEP 479)."""
        return next(get_db())

    def _queue_sessions(self):
        """Yield ``(label, session)`` for the bootstrap DB and each provisioned
        tenant DB.  The bootstrap DB is ALWAYS drained (single-tenant mode +
        unbound hosts whose messages live there); tenant DBs are drained only
        when multi-tenancy is enabled."""
        # Bootstrap / main application DB — always.
        yield ("bootstrap", self._bootstrap_session())

        if not config.is_multitenancy_enabled():
            return

        # Per-tenant queues.  Bounded by the number of provisioned tenants; a
        # tenant whose engine can't be resolved this cycle is logged and skipped
        # (never silently dropped — its queue just waits for the next cycle).
        for tenant_id in self._provisioned_tenant_ids():
            try:
                engine = resolve_engine(partition=PARTITION_TENANT, tenant_id=tenant_id)
            except Exception:  # noqa: BLE001
                logger.error(
                    "queue fan-out: could not resolve the database engine for "
                    "tenant %s; skipping its queue this cycle (is the licensed "
                    "engine loaded / the tenant provisioned?)",
                    tenant_id,
                    exc_info=True,
                )
                continue
            yield (f"tenant {tenant_id}", sessionmaker(bind=engine)())

    def _provisioned_tenant_ids(self):
        """Tenant IDs that have a provisioned database (a placement in the
        registry).  Returns ``[]`` (bootstrap-only this cycle) if the registry
        can't be read — logged, not silently swallowed."""
        try:
            with partition_session(partition=PARTITION_REGISTRY) as session:
                rows = session.query(RegistryTenantPlacement.tenant_id).distinct().all()
            return [str(tenant_id) for (tenant_id,) in rows]
        except Exception:  # noqa: BLE001
            logger.error(
                "queue fan-out: could not list provisioned tenants from the "
                "registry; draining the bootstrap DB only this cycle",
                exc_info=True,
            )
            return []


# Global message processor instance
message_processor = MessageProcessor()
