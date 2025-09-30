"""
Hardware inventory models for SysManage - storage devices and network interfaces.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class StorageDevice(Base):
    """
    Storage device inventory model for host hardware tracking.
    """

    __tablename__ = "storage_device"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    device_name = Column(String(255), nullable=False)
    device_type = Column(String(50), nullable=True)  # e.g., "SSD", "HDD", "NVMe"
    mount_point = Column(String(255), nullable=True)
    filesystem = Column(String(100), nullable=True)
    total_size_bytes = Column(BigInteger, nullable=True)
    used_size_bytes = Column(BigInteger, nullable=True)
    available_size_bytes = Column(BigInteger, nullable=True)
    device_details = Column(Text, nullable=True)  # JSON for additional device info
    last_updated = Column(DateTime, nullable=False)

    # Relationship
    host = relationship("Host")

    def __repr__(self):
        return f"<StorageDevice(id={self.id}, device_name='{self.device_name}', host_id={self.host_id})>"


class NetworkInterface(Base):
    """
    Network interface inventory model for host hardware tracking.
    """

    __tablename__ = "network_interface"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    interface_name = Column(String(255), nullable=False)
    interface_type = Column(
        String(50), nullable=True
    )  # e.g., "ethernet", "wifi", "loopback"
    mac_address = Column(String(17), nullable=True)
    ipv4_address = Column(String(15), nullable=True)
    ipv6_address = Column(String(39), nullable=True)
    netmask = Column(String(15), nullable=True)
    broadcast = Column(String(15), nullable=True)
    mtu = Column(Integer, nullable=True)
    speed_mbps = Column(Integer, nullable=True)
    is_up = Column(Boolean, nullable=True)
    interface_details = Column(
        Text, nullable=True
    )  # JSON for additional interface info
    last_updated = Column(DateTime, nullable=False)

    # Relationship
    host = relationship("Host")

    def __repr__(self):
        return f"<NetworkInterface(id={self.id}, interface_name='{self.interface_name}', host_id={self.host_id})>"
