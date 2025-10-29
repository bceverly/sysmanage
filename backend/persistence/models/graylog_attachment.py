"""
Graylog attachment model for tracking host connectivity to Graylog.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class GraylogAttachment(Base):
    """
    Model to store Graylog attachment status for hosts.

    Tracks whether a host is forwarding logs to Graylog and via what mechanism.
    """

    __tablename__ = "graylog_attachment"

    id = Column(GUID(), primary_key=True, default=uuid4)
    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    is_attached = Column(Boolean, default=False, nullable=False)
    target_hostname = Column(String(255), nullable=True)
    target_ip = Column(String(45), nullable=True)  # IPv6 max length is 45 chars
    mechanism = Column(
        String(50), nullable=True
    )  # syslog_tcp, syslog_udp, gelf_tcp, windows_sidecar
    port = Column(Integer, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship to host
    host = relationship("Host", back_populates="graylog_attachment")

    def __repr__(self):
        return f"<GraylogAttachment(host_id={self.host_id}, is_attached={self.is_attached}, mechanism={self.mechanism})>"

    def to_dict(self) -> dict:
        """Convert the Graylog attachment to a dictionary."""
        return {
            "id": str(self.id),
            "host_id": str(self.host_id),
            "is_attached": self.is_attached,
            "target_hostname": self.target_hostname,
            "target_ip": self.target_ip,
            "mechanism": self.mechanism,
            "port": self.port,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
