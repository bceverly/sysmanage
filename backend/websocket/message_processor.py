"""
Background message processor for SysManage.
Processes queued messages from agents asynchronously.
"""

import asyncio

from backend.i18n import _
from backend.persistence.db import get_db
from backend.utils.verbosity_logger import get_logger
from backend.websocket.inbound_processor import process_pending_messages
from backend.websocket.outbound_processor import process_outbound_messages

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
                    logger.error(
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
        finally:
            self.running = False
            logger.info(_("Message processor stopped"))

    def stop(self):
        """Stop the background message processing."""
        self.running = False

    async def _process_pending_messages(self):
        """Process all pending messages in the queue."""
        db = next(get_db())

        try:
            # Process inbound messages (from agents to server)
            await process_pending_messages(db)

            # Process outbound messages (from server to agents)
            await process_outbound_messages(db)

            # Commit all changes made during this processing cycle
            db.commit()
            logger.debug("Committed all message processing changes to database")

        except Exception as e:
            logger.error("Error during message processing, rolling back: %s", str(e))
            db.rollback()
            raise
        finally:
            db.close()


# Global message processor instance
message_processor = MessageProcessor()
