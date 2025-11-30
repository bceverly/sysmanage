"""
Helper functions, models, and constants for firewall role management.
This module contains Pydantic models, validation logic, and utility functions
used by the firewall_roles API endpoints.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.websocket.messages import CommandType, Message, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

queue_ops = QueueOperations()


# Common ports for the dropdown
COMMON_PORTS = [
    {"port": 22, "name": "SSH", "default_protocol": "tcp"},
    {"port": 80, "name": "HTTP", "default_protocol": "tcp"},
    {"port": 443, "name": "HTTPS", "default_protocol": "tcp"},
    {"port": 21, "name": "FTP", "default_protocol": "tcp"},
    {"port": 25, "name": "SMTP", "default_protocol": "tcp"},
    {"port": 53, "name": "DNS", "default_protocol": "both"},
    {"port": 110, "name": "POP3", "default_protocol": "tcp"},
    {"port": 143, "name": "IMAP", "default_protocol": "tcp"},
    {"port": 993, "name": "IMAPS", "default_protocol": "tcp"},
    {"port": 995, "name": "POP3S", "default_protocol": "tcp"},
    {"port": 3306, "name": "MySQL", "default_protocol": "tcp"},
    {"port": 5432, "name": "PostgreSQL", "default_protocol": "tcp"},
    {"port": 6379, "name": "Redis", "default_protocol": "tcp"},
    {"port": 27017, "name": "MongoDB", "default_protocol": "tcp"},
    {"port": 8080, "name": "HTTP Alt", "default_protocol": "tcp"},
    {"port": 8443, "name": "HTTPS Alt", "default_protocol": "tcp"},
    {"port": 3389, "name": "RDP", "default_protocol": "tcp"},
    {"port": 5900, "name": "VNC", "default_protocol": "tcp"},
    {"port": 123, "name": "NTP", "default_protocol": "udp"},
    {"port": 161, "name": "SNMP", "default_protocol": "udp"},
    {"port": 514, "name": "Syslog", "default_protocol": "udp"},
    {"port": 1194, "name": "OpenVPN", "default_protocol": "udp"},
    {"port": 51820, "name": "WireGuard", "default_protocol": "udp"},
]


# ============================================================================
# Pydantic Models
# ============================================================================


class PortResponse(BaseModel):
    """Response model for a port entry."""

    id: str
    port_number: int
    tcp: bool
    udp: bool
    ipv4: bool
    ipv6: bool

    @validator("id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class FirewallRoleResponse(BaseModel):
    """Response model for a firewall role."""

    id: str
    name: str
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    open_ports: List[PortResponse] = []

    @validator("id", "created_by", "updated_by", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class PortCreate(BaseModel):
    """Request model for creating a port entry."""

    port_number: int
    tcp: bool = True
    udp: bool = False
    ipv4: bool = True
    ipv6: bool = True

    @validator("port_number")
    def validate_port_number(cls, port_number):  # pylint: disable=no-self-argument
        """Validate port number is in valid range. Port 0 means 'any port'."""
        if port_number < 0 or port_number > 65535:
            raise ValueError(
                _("Port number must be between 0 and 65535 (0 means any port)")
            )
        return port_number

    @validator("udp")
    def validate_protocol(cls, udp, values):  # pylint: disable=no-self-argument
        """Validate that at least one protocol is selected."""
        tcp = values.get("tcp", True)
        if not tcp and not udp:
            raise ValueError(_("At least one protocol (TCP or UDP) must be selected"))
        return udp

    @validator("ipv6")
    def validate_ip_version(cls, ipv6, values):  # pylint: disable=no-self-argument
        """Validate that at least one IP version is selected."""
        ipv4 = values.get("ipv4", True)
        if not ipv4 and not ipv6:
            raise ValueError(
                _("At least one IP version (IPv4 or IPv6) must be selected")
            )
        return ipv6


class FirewallRoleCreate(BaseModel):
    """Request model for creating a firewall role."""

    name: str
    open_ports: List[PortCreate] = []

    @validator("name")
    def validate_name(cls, name):  # pylint: disable=no-self-argument
        """Validate role name."""
        if not name or name.strip() == "":
            raise ValueError(_("Firewall role name is required"))
        if len(name.strip()) > 100:
            raise ValueError(_("Firewall role name must be 100 characters or less"))
        return name.strip()


class FirewallRoleUpdate(BaseModel):
    """Request model for updating a firewall role."""

    name: Optional[str] = None
    open_ports: Optional[List[PortCreate]] = None

    @validator("name")
    def validate_name(cls, name):  # pylint: disable=no-self-argument
        """Validate role name if provided."""
        if name is not None:
            if name.strip() == "":
                raise ValueError(_("Firewall role name cannot be empty"))
            if len(name.strip()) > 100:
                raise ValueError(_("Firewall role name must be 100 characters or less"))
            return name.strip()
        return name


class CommonPortsResponse(BaseModel):
    """Response model for common ports."""

    ports: List[dict]


class HostFirewallRoleResponse(BaseModel):
    """Response model for a host firewall role assignment."""

    id: str
    firewall_role_id: str
    firewall_role_name: str
    created_at: datetime

    @validator("id", "firewall_role_id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class HostFirewallRoleCreate(BaseModel):
    """Request model for assigning a firewall role to a host."""

    firewall_role_id: str


# ============================================================================
# Helper Functions
# ============================================================================


def get_host_firewall_ports(db_session: Session, host_id) -> dict:
    """
    Get all open ports for a host from all assigned firewall roles.

    Returns a dict with:
    - ipv4_ports: list of {port, tcp, udp} for IPv4
    - ipv6_ports: list of {port, tcp, udp} for IPv6
    """
    # Get all firewall role assignments for this host
    assignments = (
        db_session.query(models.HostFirewallRole)
        .filter(models.HostFirewallRole.host_id == host_id)
        .all()
    )

    ipv4_ports = []
    ipv6_ports = []

    for assignment in assignments:
        # Get the firewall role with its open ports
        role = assignment.firewall_role
        if role:
            for port in role.open_ports:
                port_entry = {
                    "port": port.port_number,
                    "tcp": port.tcp,
                    "udp": port.udp,
                }
                if port.ipv4:
                    # Avoid duplicates
                    if port_entry not in ipv4_ports:
                        ipv4_ports.append(port_entry)
                if port.ipv6:
                    # Avoid duplicates
                    if port_entry not in ipv6_ports:
                        ipv6_ports.append(port_entry)

    return {
        "ipv4_ports": ipv4_ports,
        "ipv6_ports": ipv6_ports,
    }


def queue_apply_firewall_roles(db_session: Session, host: models.Host) -> None:
    """
    Queue a message to apply firewall roles to a host.

    This collects all open ports from all assigned firewall roles
    and sends them to the agent to be applied to the firewall.
    """
    # Get all ports from all assigned roles
    ports = get_host_firewall_ports(db_session, host.id)

    # Create the command message
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_FIREWALL_ROLES,
            "parameters": {
                "ipv4_ports": ports["ipv4_ports"],
                "ipv6_ports": ports["ipv6_ports"],
            },
            "timeout": 300,
        },
    )

    # Queue the message for delivery to the agent
    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db_session,
    )

    logger.info(
        "Queued apply_firewall_roles command for host %s with %d IPv4 ports and %d IPv6 ports",
        host.fqdn,
        len(ports["ipv4_ports"]),
        len(ports["ipv6_ports"]),
    )


def get_role_ports(firewall_role: models.FirewallRole) -> dict:
    """
    Get the open ports from a specific firewall role.

    Returns a dict with:
    - ipv4_ports: list of {port, tcp, udp} for IPv4
    - ipv6_ports: list of {port, tcp, udp} for IPv6
    """
    ipv4_ports = []
    ipv6_ports = []

    for port in firewall_role.open_ports:
        port_entry = {
            "port": port.port_number,
            "tcp": port.tcp,
            "udp": port.udp,
        }
        if port.ipv4:
            ipv4_ports.append(port_entry)
        if port.ipv6:
            ipv6_ports.append(port_entry)

    return {
        "ipv4_ports": ipv4_ports,
        "ipv6_ports": ipv6_ports,
    }


def queue_remove_firewall_ports(
    db_session: Session, host: models.Host, ports_to_remove: dict
) -> None:
    """
    Queue a message to remove specific firewall ports from a host.

    This sends only the specific ports to be removed to the agent,
    rather than syncing to a desired state.
    """
    # Create the command message
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.REMOVE_FIREWALL_PORTS,
            "parameters": {
                "ipv4_ports": ports_to_remove["ipv4_ports"],
                "ipv6_ports": ports_to_remove["ipv6_ports"],
            },
            "timeout": 300,
        },
    )

    # Queue the message for delivery to the agent
    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db_session,
    )

    logger.info(
        "Queued remove_firewall_ports command for host %s with %d IPv4 ports "
        "and %d IPv6 ports to remove",
        host.fqdn,
        len(ports_to_remove["ipv4_ports"]),
        len(ports_to_remove["ipv6_ports"]),
    )


def update_firewall_status_remove_ports(
    db_session: Session, host_id, ports_to_remove: dict
) -> None:
    """
    Update the firewall_status table to immediately reflect removed ports.

    This is called when a firewall role is removed, so the UI immediately
    reflects the change without waiting for the agent round-trip.
    """
    import json

    # Get the current firewall status
    firewall_status = (
        db_session.query(models.FirewallStatus)
        .filter(models.FirewallStatus.host_id == host_id)
        .first()
    )

    if not firewall_status:
        logger.warning(
            "No firewall_status record found for host %s, skipping immediate update",
            host_id,
        )
        return

    # Build set of ports to remove for quick lookup
    # ports_to_remove format: {"ipv4_ports": [{"port": 25, "tcp": True, "udp": False}], ...}
    ipv4_ports_to_remove = set()
    for port_entry in ports_to_remove.get("ipv4_ports", []):
        port_num = port_entry["port"]
        if port_entry.get("tcp"):
            ipv4_ports_to_remove.add((str(port_num), "tcp"))
        if port_entry.get("udp"):
            ipv4_ports_to_remove.add((str(port_num), "udp"))

    ipv6_ports_to_remove = set()
    for port_entry in ports_to_remove.get("ipv6_ports", []):
        port_num = port_entry["port"]
        if port_entry.get("tcp"):
            ipv6_ports_to_remove.add((str(port_num), "tcp"))
        if port_entry.get("udp"):
            ipv6_ports_to_remove.add((str(port_num), "udp"))

    # Filter IPv4 ports (stored as JSON string)
    # Format: [{"port": "22", "protocols": ["tcp"]}, {"port": "80", "protocols": ["tcp", "udp"]}]
    if firewall_status.ipv4_ports:
        try:
            current_ports = json.loads(firewall_status.ipv4_ports)
            new_ports = []
            for port_entry in current_ports:
                port = port_entry.get("port")
                protocols = port_entry.get("protocols", [])
                # Filter out protocols that should be removed
                remaining_protocols = []
                for proto in protocols:
                    if (str(port), proto) not in ipv4_ports_to_remove:
                        remaining_protocols.append(proto)
                # Only keep the port if it still has at least one protocol
                if remaining_protocols:
                    new_ports.append({"port": port, "protocols": remaining_protocols})
            firewall_status.ipv4_ports = json.dumps(new_ports) if new_ports else None
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to parse ipv4_ports JSON: %s", exc)

    # Filter IPv6 ports (stored as JSON string)
    if firewall_status.ipv6_ports:
        try:
            current_ports = json.loads(firewall_status.ipv6_ports)
            new_ports = []
            for port_entry in current_ports:
                port = port_entry.get("port")
                protocols = port_entry.get("protocols", [])
                # Filter out protocols that should be removed
                remaining_protocols = []
                for proto in protocols:
                    if (str(port), proto) not in ipv6_ports_to_remove:
                        remaining_protocols.append(proto)
                # Only keep the port if it still has at least one protocol
                if remaining_protocols:
                    new_ports.append({"port": port, "protocols": remaining_protocols})
            firewall_status.ipv6_ports = json.dumps(new_ports) if new_ports else None
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to parse ipv6_ports JSON: %s", exc)

    logger.info(
        "Immediately updated firewall_status for host %s: "
        "removed %d IPv4 port entries, removed %d IPv6 port entries",
        host_id,
        len(ipv4_ports_to_remove),
        len(ipv6_ports_to_remove),
    )


def role_to_response_dict(role: models.FirewallRole) -> dict:
    """Convert a FirewallRole model to a response dictionary."""
    return {
        "id": str(role.id),
        "name": role.name,
        "created_at": role.created_at,
        "created_by": str(role.created_by) if role.created_by else None,
        "updated_at": role.updated_at,
        "updated_by": str(role.updated_by) if role.updated_by else None,
        "open_ports": [
            {
                "id": str(p.id),
                "port_number": p.port_number,
                "tcp": p.tcp,
                "udp": p.udp,
                "ipv4": p.ipv4,
                "ipv6": p.ipv6,
            }
            for p in role.open_ports
        ],
    }
