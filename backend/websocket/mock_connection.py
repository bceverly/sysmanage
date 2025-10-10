"""
Mock connection object for SysManage message handlers.
Provides a mock WebSocket connection for use during queue processing.
"""

from typing import Any, Dict

from backend.i18n import _
from backend.utils.verbosity_logger import get_logger

logger = get_logger(__name__)


class MockConnection:
    """Mock connection object for message handlers that expect a WebSocket connection."""

    def __init__(self, host_id: str):
        """
        Initialize a mock connection.

        Args:
            host_id: The ID of the host this connection represents
        """
        self.host_id = host_id
        self.hostname = None  # Will be populated by handlers if needed
        self.is_mock_connection = True  # Flag to prevent last_access updates

    async def send_message(self, message: Dict[str, Any]):
        """
        Mock send_message method - messages are not sent back during queue processing.

        Args:
            message: The message that would be sent (ignored in mock)
        """
        logger.debug(
            _("Mock connection: would send message %s"),
            message.get("message_type", "unknown"),
        )
