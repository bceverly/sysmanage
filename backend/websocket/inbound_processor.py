# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Inbound message processor for SysManage.
Handles processing of messages received from agents.
"""

import asyncio
import random
import threading
import time
import zlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session, sessionmaker

from backend.i18n import _
from backend.startup.leadership import leadership, multi_process
from backend.utils.verbosity_logger import get_logger
from backend.websocket import report_window
from backend.websocket.message_router import log_message_data, route_inbound_message
from backend.websocket.mock_connection import MockConnection
from backend.websocket.queue_manager import (
    QueueDirection,
    QueueStatus,
    server_queue_manager,
)

logger = get_logger(__name__)


def _resolve_host_via_index(host_id):
    """Fast path: resolve a host straight from the host→tenant index.

    Returns ``(host, session)`` with the tenant session left OPEN (caller must
    close it), or ``(None, None)`` when there's no host_id, the index can't
    resolve a tenant, or the host isn't in that tenant DB.
    """
    if not host_id:
        return None, None

    from backend.persistence.models import Host  # noqa: PLC0415
    from backend.persistence.partitions import tenant_engine_for_host  # noqa: PLC0415

    try:
        engine = tenant_engine_for_host(host_id)
    except Exception:  # noqa: BLE001 -- fall through to the scan in the caller
        engine = None
    if engine is None:
        return None, None

    session = sessionmaker(bind=engine)()
    host = session.query(Host).filter(Host.id == host_id).first()
    if host is not None:
        return host, session
    session.close()
    return None, None


def _match_host_in_session(session, host_id, hostname):
    """Return the host matching ``host_id`` (then case-insensitive fqdn) in
    ``session``'s database, or ``None``."""
    from sqlalchemy import func  # noqa: PLC0415

    from backend.persistence.models import Host  # noqa: PLC0415

    host = None
    if host_id:
        host = session.query(Host).filter(Host.id == host_id).first()
    if not host and hostname:
        host = (
            session.query(Host)
            .filter(func.lower(Host.fqdn) == hostname.lower())
            .first()
        )
    return host


def _find_host_in_tenant_dbs(host_id, hostname):
    """Search every provisioned TENANT database for a host (by id, then fqdn).

    Phase 13.1: inbound messages are enqueued to the bootstrap queue with no
    host_id, but a tenant host's row lives in its tenant DB -- so the bootstrap
    pass can't find it.  This resolves the host in the tenant databases.

    Returns ``(host, session)`` with the session left OPEN (the caller processes
    the message against it, then MUST close it), or ``(None, None)`` when the
    host isn't in any tenant DB / multi-tenancy is off.  The bootstrap database
    is skipped here -- the caller has already checked it.

    Resolution mirrors ``handle_system_info``: the host→tenant INDEX is the
    authoritative source (keyed by host_id), so try it first; fall back to
    scanning the tenant databases by fqdn for hostname-only messages or when the
    index lags.
    """
    from backend.persistence.partitions import iter_host_databases  # noqa: PLC0415

    # Authoritative fast path: the index resolves the owning tenant from host_id.
    host, session = _resolve_host_via_index(host_id)
    if host is not None:
        return host, session

    # Fallback: scan every tenant database (covers hostname-only messages and a
    # host whose index binding hasn't landed yet).
    for _label, tenant_id, session in iter_host_databases():
        if tenant_id is None:  # bootstrap -- already checked by the caller
            session.close()
            continue
        host = _match_host_in_session(session, host_id, hostname)
        if host is not None:
            return host, session
        session.close()
    return None, None


async def _dispatch_null_host_message(message, host, db, hostname, tenant_session):
    """Validate a resolved NULL-host message and process it, then close the
    (optional) tenant session the host was resolved on.

    Split out of ``process_pending_messages`` so the resolve/validate/dispatch
    branches don't pile cognitive complexity onto the queue loop.  A ``continue``
    in the caller's loop becomes a ``return`` here.
    """
    try:
        if not host:
            logger.warning(
                _("Host %(hostname)s not found for message %(message_id)s, deleting"),
                {"hostname": hostname, "message_id": message.message_id},
            )
            server_queue_manager.mark_failed(
                message.message_id, f"Host {hostname} not found", db=db
            )
            return

        if host.approval_status != "approved":
            logger.warning(
                _(
                    "Host %(hostname)s not approved (status: %(status)s) for message %(message_id)s, deleting"
                ),
                {
                    "hostname": hostname,
                    "status": host.approval_status,
                    "message_id": message.message_id,
                },
            )
            server_queue_manager.mark_failed(
                message.message_id, f"Host {hostname} not approved", db=db
            )
            return

        # Host is valid and approved - process the message.  Handler writes go to
        # tenant_session when the host is in a tenant DB.
        logger.info(
            _(
                "Processing NULL host_id message for approved host %(hostname)s (ID: %(host_id)s)"
            ),
            {"hostname": hostname, "host_id": host.id},
        )
        await process_validated_message(message, host, db, host_db=tenant_session)
    finally:
        if tenant_session is not None:
            tenant_session.close()


# Phase 22.2 intake throughput.  The drain used to take 10 host-less messages a
# second for the whole server (plus 10 hosts x 10 messages): the scale harness
# watched a 1,000-agent fleet queue 52,000 messages it could not catch up on.
# Now each call drains until its time budget is spent, oldest-waiting host
# first, yielding between messages so the WebSockets keep breathing.
INBOUND_BUDGET_SECONDS = 0.75
HOST_BATCH = 50  # hosts claimed per round, oldest waiting first
PER_HOST_LIMIT = 20  # messages per host per round, so no host starves the rest
NULL_HOST_BATCH = 50
STUCK_SECONDS = 30
EXPIRY_INTERVAL_SECONDS = 30.0
_last_expiry = float("-inf")
STUCK_SECONDS_MULTI = 300
# Namespace (first key) of the per-host drain locks; the leader lock uses the
# one-key form, which PostgreSQL keeps apart from the two-key form.
HOST_LOCK_CLASS = 0x534D


class _HostLocks:
    """Per-host drain locks across server processes (Phase 22.2).

    With several workers, each drains the queue; two of them must never
    process one host's messages at once (out of order, and racing on that
    host's rows).  A worker drains a host only while it holds that host's
    PostgreSQL advisory lock, on one connection kept for the drain.  One
    process, or a database without advisory locks: every acquire succeeds."""

    def __init__(self, db):
        self._conn = None
        bind = db.get_bind()
        self._dialect = bind.dialect.name
        if multi_process() and bind.dialect.name == "postgresql":
            self._conn = bind.connect().execution_options(isolation_level="AUTOCOMMIT")

    @property
    def active(self) -> bool:
        return self._conn is not None

    @property
    def exclusive(self) -> bool:
        """True when a host this drain acquired can be processed by nobody
        else: every worker takes the same lock, or SQLite (one process).
        One PostgreSQL worker takes no locks, and a worker joining mid-drain
        would not wait for it -- there the per-message claim still guards."""
        return self.active or self._dialect == "sqlite"

    @staticmethod
    def _key(host_id) -> int:
        return zlib.crc32(str(host_id).encode("utf-8")) - 2**31  # a signed int4

    def acquire(self, host_id) -> bool:
        if self._conn is None:
            return True
        return bool(
            self._conn.execute(
                text("SELECT pg_try_advisory_lock(:c, :k)"),
                {"c": HOST_LOCK_CLASS, "k": self._key(host_id)},
            ).scalar()
        )

    def release(self, host_id) -> None:
        if self._conn is not None:
            self._conn.execute(
                text("SELECT pg_advisory_unlock(:c, :k)"),
                {"c": HOST_LOCK_CLASS, "k": self._key(host_id)},
            )

    def close(self) -> None:
        if self._conn is None:
            return
        conn, self._conn = self._conn, None
        try:
            conn.execute(text("SELECT pg_advisory_unlock_all()"))
            conn.close()
        except Exception:  # pylint: disable=broad-exception-caught
            conn.invalidate()  # never return a connection that may hold locks


def _reset_stuck_messages(db):
    """Put abandoned IN_PROGRESS messages back to PENDING.  One process: any
    IN_PROGRESS row older than 30 s is abandoned (the drain is sequential).
    Several: another worker may still be working on it, so wait longer."""
    from backend.persistence.models import MessageQueue  # noqa: PLC0415

    stuck_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=STUCK_SECONDS_MULTI if multi_process() else STUCK_SECONDS
    )
    stuck_messages = (
        db.query(MessageQueue)
        .filter(
            MessageQueue.direction == QueueDirection.INBOUND,
            MessageQueue.status == QueueStatus.IN_PROGRESS,
            MessageQueue.started_at < stuck_threshold,
        )
        .all()
    )
    if stuck_messages:
        logger.warning(
            "Found %s stuck IN_PROGRESS messages, resetting to PENDING",
            len(stuck_messages),
        )
        for msg in stuck_messages:
            msg.status = QueueStatus.PENDING
            msg.started_at = None
        db.commit()


def _due_filter(MessageQueue):  # pylint: disable=invalid-name
    """Pending, unexpired inbound rows whose retry time (if any) has come."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return and_(
        MessageQueue.direction == QueueDirection.INBOUND,
        MessageQueue.status == QueueStatus.PENDING,
        MessageQueue.expired_at.is_(None),
        or_(MessageQueue.scheduled_at.is_(None), MessageQueue.scheduled_at <= now),
    )


# Phase 22.2: one read of the oldest waiting hosts serves several rounds.
# Read every round, it was the database's costliest statement at 10,000
# agents (24-28 ms: up to 4,000 rows to find 200 hosts).  A host listed here
# whose messages are already done costs one indexed lookup; a host that
# started waiting since the read waits at most HOST_WINDOW_SECONDS.
HOST_WINDOW_SECONDS = 5.0
_host_windows = {}  # database -> (read_at, [host_id, ...] still to serve)
_host_windows_lock = threading.Lock()


def _window_key(db) -> str:
    return str(db.get_bind().url)


def _host_window_cached(db) -> bool:
    with _host_windows_lock:
        read_at, hosts = _host_windows.get(_window_key(db), (0.0, []))
    return bool(hosts) and time.monotonic() - read_at < HOST_WINDOW_SECONDS


def forget_host_window(db=None) -> None:
    """Drop the cached window (one database's, or all) so the next round reads."""
    with _host_windows_lock:
        if db is None:
            _host_windows.clear()
        else:
            _host_windows.pop(_window_key(db), None)


def _oldest_waiting_hosts(db, limit):
    """The next ``limit`` hosts to drain, oldest waiting first."""
    from backend.persistence.models import MessageQueue  # noqa: PLC0415

    key = _window_key(db)
    now = time.monotonic()
    with _host_windows_lock:
        read_at, hosts = _host_windows.get(key, (0.0, []))
        if hosts and now - read_at < HOST_WINDOW_SECONDS:
            _host_windows[key] = (read_at, hosts[limit:])
            return hosts[:limit]
    if multi_process():
        # Every worker sees the same oldest hosts; a wider, shuffled window
        # spreads them so workers do not queue up on one another's locks.
        hosts = _oldest_waiting_hosts_window(db, MessageQueue, limit * 4)
        random.shuffle(hosts)
    else:
        hosts = _oldest_waiting_hosts_window(db, MessageQueue, limit * 4)
    with _host_windows_lock:
        _host_windows[key] = (now, hosts[limit:])
    return hosts[:limit]


def _oldest_waiting_hosts_window(
    db, MessageQueue, limit
):  # pylint: disable=invalid-name
    """The ``limit`` hosts whose oldest due message is oldest.

    Read due rows oldest first and keep each host's first appearance -- that
    is its oldest row, so the order is exactly min(created_at) per host --
    stopping after ``limit * PER_HOST_LIMIT`` rows.  It was a GROUP BY over
    every pending row: 61 ms a round with 100k waiting at 10,000 agents
    (2026-10-02), 27% of the database's time.  This walks the index
    ``ix_message_queue_drain_order`` instead.  Rows that cover fewer than
    ``limit`` hosts give fewer hosts: still the oldest ones."""
    hosts = {}
    for (host_id,) in (
        db.query(MessageQueue.host_id)
        .filter(_due_filter(MessageQueue), MessageQueue.host_id.is_not(None))
        .order_by(MessageQueue.created_at)
        .limit(limit * PER_HOST_LIMIT)
    ):
        hosts.setdefault(host_id, None)
        if len(hosts) >= limit:
            break
    return list(hosts)


def _defer_messages_of_missing_host(db, host_id):
    """Phase 13.1 #2 SAFETY: never hard-delete on "host not found" -- under
    per-tenant queues a freshly enrolled host's row may not be visible yet.
    Each message is deferred via mark_failed(retry) and only gives up after
    max_retries, left as FAILED and inspectable rather than gone."""
    from backend.persistence.models import MessageQueue  # noqa: PLC0415

    pending = (
        db.query(MessageQueue)
        .filter(
            MessageQueue.host_id == host_id,
            MessageQueue.direction == QueueDirection.INBOUND,
            MessageQueue.status == QueueStatus.PENDING,
        )
        .all()
    )
    logger.warning(
        _(
            "Host %(host_id)s not found on this database; deferring %(count)d queued "
            "message(s) for retry (NOT deleting) -- may be an in-flight "
            "enrollment or a deleted host"
        ),
        {"host_id": host_id, "count": len(pending)},
    )
    for message in pending:
        server_queue_manager.mark_failed(
            message.message_id,
            f"Host {host_id} not found on this database (deferred for retry)",
            db=db,
        )


async def _drain_one_host(db, host_id, deadline, seen, exclusive=False) -> int:
    """Process this host's due messages; returns how many were attempted."""
    from backend.persistence.models import Host  # noqa: PLC0415

    host = db.query(Host).filter(Host.id == host_id).first()
    if not host:
        _defer_messages_of_missing_host(db, host_id)
        return 0
    if host.approval_status != "approved":
        logger.warning(
            _(
                "Host %(host_id)s (FQDN: %(fqdn)s) no longer approved (status: %(status)s), deleting all its messages from queue"
            ),
            {"host_id": host_id, "fqdn": host.fqdn, "status": host.approval_status},
        )
        deleted = server_queue_manager.delete_messages_for_host(host_id, db=db)
        logger.info(
            _("Deleted %(count)d messages for unapproved host %(host_id)s"),
            {"count": deleted, "host_id": host_id},
        )
        return 0
    attempted = 0
    for message in server_queue_manager.dequeue_messages_for_host(
        host_id=host_id, direction=QueueDirection.INBOUND, limit=PER_HOST_LIMIT, db=db
    ):
        # At most one attempt per message per drain: its outcome (completed,
        # failed, retry scheduled) is written through other sessions, so this
        # session can still see it as pending -- re-taking it would retry it
        # at once instead of after its backoff.
        if message.message_id in seen:
            continue
        seen.add(message.message_id)
        attempted += 1
        await process_validated_message(message, host, db, claimed=exclusive)
        report_window.record_processed(1)
        await asyncio.sleep(0)  # let the WebSockets and heartbeats run
        if time.monotonic() >= deadline:
            break
    return attempted


async def _drain_host_queues(db, deadline) -> bool:
    """Round after round of the oldest-waiting hosts until the budget is
    spent.  True when it stopped with work still waiting; a round that
    attempts nothing new ends the drain (the next one starts fresh)."""
    seen = set()
    locks = _HostLocks(db)
    try:
        fresh_read = False  # did this round's hosts come from a new read?
        while time.monotonic() < deadline:
            fresh_read = not _host_window_cached(db)
            host_ids = _oldest_waiting_hosts(db, HOST_BATCH)
            if not host_ids:
                if fresh_read:
                    return False
                forget_host_window(db)  # the cached window ran dry: read again
                continue
            attempted = 0
            for host_id in host_ids:
                if time.monotonic() >= deadline:
                    return True
                if not locks.acquire(host_id):
                    continue  # another worker is draining this host
                try:
                    attempted += await _drain_one_host(
                        db, host_id, deadline, seen, exclusive=locks.exclusive
                    )
                    if locks.active:
                        db.commit()  # visible before another worker takes the host
                finally:
                    locks.release(host_id)
            if not attempted:
                if fresh_read:
                    return False
                # Hosts from an older read may be done already: read again
                # before deciding there is no work.
                forget_host_window(db)
        return True
    finally:
        locks.close()


async def process_pending_messages(db: Session) -> bool:
    """Process pending inbound messages within this call's time budget.

    Returns True when it stopped with work still waiting, so the caller can
    come straight back instead of sleeping.
    """
    # Expire cached objects so queries see fresh data.
    db.expire_all()

    # Expiry is maintenance: at most every EXPIRY_INTERVAL_SECONDS per worker
    # (Phase 22.2: on every drain it was 4.4% of the drain's time at 10k).
    global _last_expiry  # pylint: disable=global-statement
    if time.monotonic() - _last_expiry >= EXPIRY_INTERVAL_SECONDS:
        _last_expiry = time.monotonic()
        expired_count = server_queue_manager.expire_old_messages(db)
        if expired_count > 0:
            logger.info("Expired %d old messages", expired_count)

    _reset_stuck_messages(db)
    deadline = time.monotonic() + INBOUND_BUDGET_SECONDS
    more = await _drain_host_queues(db, deadline)
    if multi_process() and not leadership.is_leader:
        return more  # host-less messages: the leader's (no host to lock on)
    return await _drain_null_host_messages(db, deadline) or more


async def _drain_null_host_messages(db, deadline) -> bool:
    """Messages queued without a host (sessions from before 22.2, buffered
    pre-handshake traffic): the host is resolved from the message.  True when
    the budget ran out with more waiting."""
    from backend.persistence.models import MessageQueue  # noqa: PLC0415

    null_host_messages = (
        db.query(MessageQueue)
        .filter(_due_filter(MessageQueue), MessageQueue.host_id.is_(None))
        .order_by(MessageQueue.created_at)
        .limit(NULL_HOST_BATCH)
        .all()
    )
    for message in null_host_messages:
        if time.monotonic() >= deadline:
            return True
        await _process_null_host_message(db, message)
        await asyncio.sleep(0)
    return len(null_host_messages) == NULL_HOST_BATCH


async def _process_null_host_message(db, message) -> None:
    logger.info(_("Processing message with NULL host_id: %s"), message.message_id)

    # Deserialize message data to extract hostname
    try:
        message_data = server_queue_manager.deserialize_message_data(message)

        # Check if this is a SYSTEM_INFO message (registration) - these don't require host lookup
        from backend.websocket.messages import MessageType

        if message.message_type == MessageType.SYSTEM_INFO:
            logger.info(
                _("Processing SYSTEM_INFO registration message %s"),
                message.message_id,
            )
            # SYSTEM_INFO messages are processed without host validation
            # The handler will create/update the host record
            await process_system_info_message(message, db)
            return

        hostname = message_data.get("hostname")

        # Try connection info if no hostname in message data
        if not hostname:
            connection_info = message_data.get("_connection_info", {})
            hostname = connection_info.get("hostname")

        # Get host_id from message data (agents send this)
        host_id = message_data.get("host_id")
        if not host_id:
            connection_info = message_data.get("_connection_info", {})
            host_id = connection_info.get("host_id")

        if not hostname and not host_id:
            logger.warning(
                _("Message %s missing hostname and host_id, deleting"),
                message.message_id,
            )
            server_queue_manager.mark_failed(
                message.message_id,
                "Missing hostname and host_id in message data",
                db=db,
            )
            return

        host, tenant_session = resolve_message_host(db, host_id, hostname)

        await _dispatch_null_host_message(message, host, db, hostname, tenant_session)

    except Exception as e:
        logger.exception(
            _("Error processing NULL host_id message %(message_id)s: %(error)s"),
            {"message_id": message.message_id, "error": str(e)},
        )
        server_queue_manager.mark_failed(
            message.message_id, f"Processing error: {str(e)}", db=db
        )


def resolve_message_host(db, host_id, hostname):
    """Find the host an inbound queue message belongs to, and the session its
    data lives in.

    Returns ``(host, tenant_session)``.  ``tenant_session`` is None when the
    host was found in the bootstrap database (the caller then uses its own
    session); otherwise it is an OPEN tenant session the caller must close.

    WHY THE TWO LOOKUPS HAVE OPPOSITE PRECEDENCE
    --------------------------------------------
    ``host_id`` is resolved bootstrap-first, then across every tenant DB.  Ids
    are globally unique, so whichever database answers first is the right one.

    ``hostname`` is resolved TENANT-first, then bootstrap -- the reverse --
    because FQDNs are NOT unique across databases.  Moving a host into a tenant
    leaves its old bootstrap row behind under the same fqdn, and that stale row
    is often still ``approved``, so nothing downstream rejects it.  Resolving
    bootstrap-first therefore returns the stale row with ``tenant_session``
    None, and the handler runs against a database that does not hold the host's
    data -- succeeding, silently, having written nothing useful.

    Observed 2026-08-28: command results for a tenant-bound host were processed
    on bootstrap, where the originating command's queue row does not exist, so
    every config-profile result was discarded without an error anywhere.
    """
    from backend.persistence.models import Host  # noqa: PLC0415

    host = None
    tenant_session = None

    if host_id:
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            host, tenant_session = _find_host_in_tenant_dbs(host_id, None)

    # Only when no host_id was sent, or it resolved nowhere (e.g. a
    # hostname_changed that landed before the index caught up).
    if not host and hostname:
        host, tenant_session = _find_host_in_tenant_dbs(None, hostname)
        if not host:
            host = db.query(Host).filter(Host.fqdn == hostname).first()

    return host, tenant_session


async def process_validated_message(
    message, host, db: Session, host_db=None, claimed=False
) -> None:
    """
    Process a message with pre-validated host information.

    Args:
        message: The message queue entry to process
        host: The validated host object
        db: Database session holding the QUEUE row (queue ops run here).
        host_db: Database session holding the HOST's data (the handler's writes
            run here).  Phase 13.1: a tenant host's data lives in its tenant DB
            while its inbound message can sit in the bootstrap queue, so the two
            differ.  Defaults to ``db`` (collapsed/single-tenant mode), where
            they're the same database.
        claimed: the caller holds this host exclusively (its drain lock), so
            no other worker can take the message: skip the claim UPDATE.
            Phase 22.2 -- one write per message instead of two; a crash
            mid-message leaves it pending, to be processed again, as the
            stuck-message reset already did.
    """
    handler_db = host_db if host_db is not None else db
    try:
        logger.debug(
            "Starting to process message %s of type %s",
            message.message_id,
            message.message_type,
        )

        # Mark message as being processed
        if not claimed and not server_queue_manager.mark_processing(
            message.message_id, db=db
        ):
            logger.warning(
                _("Could not mark message %s as processing"), message.message_id
            )
            return

        # Deserialize message data
        message_data = server_queue_manager.deserialize_message_data(message)
        data_size = len(str(message_data)) if message_data else 0
        data_keys = list(message_data.keys()) if message_data else []
        logger.debug(
            "Deserialized message data - keys: %s, size: %s bytes",
            data_keys,
            data_size,
        )

        # Create connection object with host info
        mock_connection = MockConnection(host.id)
        mock_connection.hostname = host.fqdn
        mock_connection.verified_host_id = str(host.id)  # handlers skip the re-check

        logger.debug(
            _(
                "Processing queued message: %(message_id)s (type: %(message_type)s, host: %(host)s)"
            ),
            {
                "message_id": message.message_id,
                "message_type": message.message_type,
                "host": host.fqdn,
            },
        )

        # Log specific data for different message types
        log_message_data(message.message_type, message_data)

        # Route to appropriate handler based on message type.  The handler's
        # writes go to the HOST's database (handler_db) -- the tenant DB for a
        # tenant host -- even when the queue row lives in the bootstrap queue.
        success = await route_inbound_message(
            message.message_type, handler_db, mock_connection, message_data
        )

        # Persist the handler's writes on the host DB when it's a separate
        # (tenant) session -- the caller only commits the queue DB.
        if success and host_db is not None:
            host_db.commit()

        if success:
            # Mark message as completed and remove from queue
            server_queue_manager.mark_completed(message.message_id, db=db)
            logger.debug(
                _(
                    "Successfully processed and completed message: %(message_id)s for host %(host)s"
                ),
                {"message_id": message.message_id, "host": host.fqdn},
            )
        else:
            # Mark message as failed and remove from queue
            server_queue_manager.mark_failed(
                message.message_id, error_message="Unknown message type", db=db
            )
            logger.error(
                _("Failed to process message %s: unknown message type"),
                message.message_id,
            )

        # Air-gap repository auto-repoint: now that this agent has
        # communicated, ensure it's pointed at the local mirror (and off
        # the internet) when this server runs as an Air-Gap Repository.
        # Hooked HERE (not in the caller loops) because BOTH the host-id
        # and the null-host-id inbound paths funnel through this function
        # -- agents that put host_id in the message body hit the
        # null-host path, which the loop-level hook missed.  Best-effort
        # and self-throttling: a no-op unless the role is 'repository'
        # and the agent's mirror config actually needs to change.
        from backend.services import (
            airgap_repoint_service,
        )  # pylint: disable=import-outside-toplevel

        airgap_repoint_service.maybe_repoint(handler_db, host)

    except Exception as e:
        logger.exception(
            _("Error processing message %(message_id)s for host %(host)s: %(error)s"),
            {
                "message_id": message.message_id,
                "host": host.fqdn,
                "error": str(e),
            },
        )
        # Mark message as failed and remove from queue
        server_queue_manager.mark_failed(
            message.message_id, error_message=str(e), db=db
        )


async def process_system_info_message(message, db: Session) -> None:
    """
    Process a SYSTEM_INFO registration message.
    This is special because the host may not exist yet.

    Phase 13.1: this stays on the bootstrap ``db`` deliberately -- ``handle_system_info``
    SELF-ROUTES.  It resolves the host's tenant from the agent-supplied host_id
    (``tenant_engine_for_host``) and runs the whole handler on that tenant's
    database, so a bound host's inventory updates land in its tenant DB and no
    duplicate host row is created on bootstrap.  Untenanted hosts use ``db``.
    """
    try:
        logger.info("Processing SYSTEM_INFO message %s", message.message_id)

        # Mark message as being processed
        if not server_queue_manager.mark_processing(message.message_id, db=db):
            logger.warning(
                _("Could not mark SYSTEM_INFO message %s as processing"),
                message.message_id,
            )
            return

        # Deserialize message data
        message_data = server_queue_manager.deserialize_message_data(message)

        # Extract connection info
        connection_info = message_data.get("_connection_info", {})

        # Create a mock connection with the stored connection info
        mock_connection = MockConnection(None)  # No host_id yet
        mock_connection.agent_id = connection_info.get("agent_id")
        mock_connection.hostname = connection_info.get("hostname")
        mock_connection.ipv4 = connection_info.get("ipv4")
        mock_connection.ipv6 = connection_info.get("ipv6")
        mock_connection.platform = connection_info.get("platform")

        # Call the system_info handler.  It self-routes to the host's tenant
        # database from the agent-supplied host_id (see its docstring), so the
        # bootstrap ``db`` passed here is only used for untenanted hosts.
        from backend.api.message_handlers import handle_system_info

        await handle_system_info(db, mock_connection, message_data)

        # Mark as completed
        server_queue_manager.mark_completed(message.message_id, db=db)
        logger.info("Successfully processed SYSTEM_INFO message %s", message.message_id)

    except Exception as e:
        logger.exception(
            _("Error processing SYSTEM_INFO message %(message_id)s: %(error)s"),
            {"message_id": message.message_id, "error": str(e)},
            exc_info=True,
        )
        server_queue_manager.mark_failed(
            message.message_id, error_message=str(e), db=db
        )
