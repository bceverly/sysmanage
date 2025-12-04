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
