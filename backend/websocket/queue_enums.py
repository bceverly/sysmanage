# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Message Queue Enumerations for SysManage.
Defines status, direction, and priority enums for message queuing.
"""


class QueueStatus:
    """Message queue status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SENT = "sent"  # Message sent to agent, awaiting acknowledgment
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class QueueDirection:
    """Message queue direction enumeration."""

    OUTBOUND = "outbound"  # Messages to send to agents
    INBOUND = "inbound"  # Messages received from agents


class Priority:
    """Message priority enumeration."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
