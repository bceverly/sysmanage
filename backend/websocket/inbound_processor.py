"""
Inbound message processor for SysManage.
Handles processing of messages received from agents.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.utils.verbosity_logger import get_logger
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

    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence.models import Host  # noqa: PLC0415
    from backend.persistence.partitions import (  # noqa: PLC0415
        tenant_engine_for_host,
    )

    try:
        engine = tenant_engine_for_host(host_id)
    except Exception:  # noqa: BLE001 — fall through to the scan in the caller
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
    host_id, but a tenant host's row lives in its tenant DB — so the bootstrap
    pass can't find it.  This resolves the host in the tenant databases.

    Returns ``(host, session)`` with the session left OPEN (the caller processes
    the message against it, then MUST close it), or ``(None, None)`` when the
    host isn't in any tenant DB / multi-tenancy is off.  The bootstrap database
    is skipped here — the caller has already checked it.

    Resolution mirrors ``handle_system_info``: the host→tenant INDEX is the
    authoritative source (keyed by host_id), so try it first; fall back to
    scanning the tenant databases by fqdn for hostname-only messages or when the
    index lags.
    """
    from backend.persistence.partitions import (  # noqa: PLC0415
        iter_host_databases,
    )

    # Authoritative fast path: the index resolves the owning tenant from host_id.
    host, session = _resolve_host_via_index(host_id)
    if host is not None:
        return host, session

    # Fallback: scan every tenant database (covers hostname-only messages and a
    # host whose index binding hasn't landed yet).
    for _label, tenant_id, session in iter_host_databases():
        if tenant_id is None:  # bootstrap — already checked by the caller
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
                _("Host %s not found for message %s, deleting"),
                hostname,
                message.message_id,
            )
            server_queue_manager.mark_failed(
                message.message_id, f"Host {hostname} not found", db=db
            )
            return

        if host.approval_status != "approved":
            logger.warning(
                _("Host %s not approved (status: %s) for message %s, deleting"),
                hostname,
                host.approval_status,
                message.message_id,
            )
            server_queue_manager.mark_failed(
                message.message_id, f"Host {hostname} not approved", db=db
            )
            return

        # Host is valid and approved - process the message.  Handler writes go to
        # tenant_session when the host is in a tenant DB.
        logger.info(
            _("Processing NULL host_id message for approved host %s (ID: %s)"),
            hostname,
            host.id,
        )
        await process_validated_message(message, host, db, host_db=tenant_session)
    finally:
        if tenant_session is not None:
            tenant_session.close()


async def process_pending_messages(  # NOSONAR
    db: Session,
) -> None:
    """
    Process all pending messages in the queue.

    Args:
        db: Database session
    """
    print("_process_pending_messages() called", flush=True)
    logger.info("_process_pending_messages() called")

    # Expire all cached objects to ensure we get fresh data from the database
    # This prevents stale objects from being returned by queries
    db.expire_all()

    print(f"Got database session: {db}", flush=True)
    logger.info("Got database session")

    # First, expire old messages to prevent infinite processing loops
    expired_count = server_queue_manager.expire_old_messages(db)
    if expired_count > 0:
        logger.info("Expired %d old messages", expired_count)

    from backend.persistence.models import Host, MessageQueue

    # Define stuck message threshold (messages older than 30 seconds)
    stuck_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=30
    )

    # First, reset stuck IN_PROGRESS messages back to PENDING
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
        print(
            f"Found {len(stuck_messages)} stuck IN_PROGRESS messages, resetting to PENDING",
            flush=True,
        )
        for msg in stuck_messages:
            msg.status = QueueStatus.PENDING
            msg.started_at = None
            print(
                f"Reset message {msg.message_id} from IN_PROGRESS back to PENDING",
                flush=True,
            )
        db.commit()

    # Now get all hosts with pending messages (including newly reset ones)
    # Exclude expired messages from processing
    host_ids = (
        db.query(MessageQueue.host_id)
        .filter(
            MessageQueue.direction == QueueDirection.INBOUND,
            MessageQueue.status == QueueStatus.PENDING,
            MessageQueue.host_id.is_not(None),
            MessageQueue.expired_at.is_(None),
        )
        .distinct()
        .limit(10)
        .all()
    )

    print(
        f"Found {len(host_ids)} hosts with pending messages",
        flush=True,
    )
    logger.info("Found %s hosts with pending messages", len(host_ids))

    for (host_id,) in host_ids:
        # Check if host exists and is still approved before processing its messages
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            # Phase 13.1 #2 SAFETY: do NOT hard-delete on "host not found".
            # Under per-tenant queues there is an enrollment race window where a
            # freshly-registered host's row may not yet be visible on THIS
            # (tenant) database even though its messages are already queued here —
            # a bulk delete would destroy the agent's data permanently.  Instead
            # defer each message via mark_failed(retry=True): it reschedules with
            # backoff (so a transient miss is reprocessed once the host row lands)
            # and only gives up after max_retries, leaving the row as FAILED and
            # still inspectable rather than gone.  A genuinely-deleted host's
            # messages therefore stop after a bounded number of attempts instead
            # of vanishing silently.
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
                    "Host %s not found on this database; deferring %d queued "
                    "message(s) for retry (NOT deleting) — may be an in-flight "
                    "enrollment or a deleted host"
                ),
                host_id,
                len(pending),
            )
            for message in pending:
                server_queue_manager.mark_failed(
                    message.message_id,
                    f"Host {host_id} not found on this database (deferred for retry)",
                    db=db,
                )
            continue

        if host.approval_status != "approved":
            logger.warning(
                _(
                    "Host %s (FQDN: %s) no longer approved (status: %s), deleting all its messages from queue"
                ),
                host_id,
                host.fqdn,
                host.approval_status,
            )
            deleted = server_queue_manager.delete_messages_for_host(host_id, db=db)
            logger.info(
                _("Deleted %d messages for unapproved host %s"),
                deleted,
                host_id,
            )
            continue

        # Host exists and is approved - process its messages
        logger.info(
            _("Processing messages for approved host %s (FQDN: %s)"),
            host_id,
            host.fqdn,
        )
        host_messages = server_queue_manager.dequeue_messages_for_host(
            host_id=host_id, direction=QueueDirection.INBOUND, limit=10, db=db
        )

        for message in host_messages:
            await process_validated_message(message, host, db)

    # Second, handle messages with NULL host_id by extracting hostname from message data
    # Exclude expired messages from processing
    null_host_messages = (
        db.query(MessageQueue)
        .filter(
            MessageQueue.direction == QueueDirection.INBOUND,
            MessageQueue.status == QueueStatus.PENDING,
            MessageQueue.host_id.is_(None),
            MessageQueue.expired_at.is_(None),
        )
        .limit(10)
        .all()
    )

    for message in null_host_messages:
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
                continue

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
                continue

            # Look up host by host_id first (more reliable, especially for
            # hostname_changed), then fall back to hostname lookup.
            host = None
            if host_id:
                host = db.query(Host).filter(Host.id == host_id).first()
            if not host and hostname:
                host = db.query(Host).filter(Host.fqdn == hostname).first()

            # Phase 13.1: a tenant host's data lives in its tenant database, but
            # this NULL-host_id message sits in the bootstrap queue (inbound
            # messages are enqueued without a host_id and resolved here).  When
            # the host isn't on THIS database, resolve it across the provisioned
            # tenant databases and run the handler against the tenant DB it lives
            # in (host_db), while the queue row stays on the bootstrap db.
            tenant_session = None
            if not host:
                host, tenant_session = _find_host_in_tenant_dbs(host_id, hostname)

            await _dispatch_null_host_message(
                message, host, db, hostname, tenant_session
            )

        except Exception as e:
            logger.exception(
                _("Error processing NULL host_id message %s: %s"),
                message.message_id,
                str(e),
            )
            server_queue_manager.mark_failed(
                message.message_id, f"Processing error: {str(e)}", db=db
            )


async def process_validated_message(message, host, db: Session, host_db=None) -> None:
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
    """
    handler_db = host_db if host_db is not None else db
    try:
        print(
            f"Starting to process message {message.message_id} of type {message.message_type}",
            flush=True,
        )
        logger.info(
            "Starting to process message %s of type %s",
            message.message_id,
            message.message_type,
        )

        # Mark message as being processed
        if not server_queue_manager.mark_processing(message.message_id, db=db):
            logger.warning(
                _("Could not mark message %s as processing"), message.message_id
            )
            return

        # Deserialize message data
        print(
            f"About to deserialize message data for {message.message_id}",
            flush=True,
        )
        message_data = server_queue_manager.deserialize_message_data(message)
        data_size = len(str(message_data)) if message_data else 0
        data_keys = list(message_data.keys()) if message_data else []
        print(
            f"Deserialized message data - keys: {data_keys}, size: {data_size} bytes",
            flush=True,
        )
        logger.info(
            "Deserialized message data - keys: %s, size: %s bytes",
            data_keys,
            data_size,
        )

        # Create connection object with host info
        mock_connection = MockConnection(host.id)
        mock_connection.hostname = host.fqdn

        logger.info(
            _("Processing queued message: %s (type: %s, host: %s)"),
            message.message_id,
            message.message_type,
            host.fqdn,
        )

        # Log specific data for different message types
        log_message_data(message.message_type, message_data)

        # Route to appropriate handler based on message type.  The handler's
        # writes go to the HOST's database (handler_db) — the tenant DB for a
        # tenant host — even when the queue row lives in the bootstrap queue.
        success = await route_inbound_message(
            message.message_type, handler_db, mock_connection, message_data
        )

        # Persist the handler's writes on the host DB when it's a separate
        # (tenant) session — the caller only commits the queue DB.
        if success and host_db is not None:
            host_db.commit()

        if success:
            # Mark message as completed and remove from queue
            print(
                f"Marking message {message.message_id} as completed",
                flush=True,
            )
            server_queue_manager.mark_completed(message.message_id, db=db)
            logger.info(
                _("Successfully processed and completed message: %s for host %s"),
                message.message_id,
                host.fqdn,
            )
            print(
                f"Message {message.message_id} marked as completed successfully",
                flush=True,
            )
        else:
            print(
                f"Message {message.message_id} processing failed",
                flush=True,
            )
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
        # — agents that put host_id in the message body hit the
        # null-host path, which the loop-level hook missed.  Best-effort
        # and self-throttling: a no-op unless the role is 'repository'
        # and the agent's mirror config actually needs to change.
        from backend.services import (  # pylint: disable=import-outside-toplevel
            airgap_repoint_service,
        )

        airgap_repoint_service.maybe_repoint(handler_db, host)

    except Exception as e:
        logger.exception(
            _("Error processing message %s for host %s: %s"),
            message.message_id,
            host.fqdn,
            str(e),
        )
        # Mark message as failed and remove from queue
        server_queue_manager.mark_failed(
            message.message_id, error_message=str(e), db=db
        )


async def process_system_info_message(message, db: Session) -> None:
    """
    Process a SYSTEM_INFO registration message.
    This is special because the host may not exist yet.

    Phase 13.1: this stays on the bootstrap ``db`` deliberately — ``handle_system_info``
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
            _("Error processing SYSTEM_INFO message %s: %s"),
            message.message_id,
            str(e),
            exc_info=True,
        )
        server_queue_manager.mark_failed(
            message.message_id, error_message=str(e), db=db
        )
