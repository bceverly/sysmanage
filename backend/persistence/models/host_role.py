"""
Host role model for tracking server roles based on installed packages and services.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class HostRole(Base):
    """
    Model to track server roles detected on hosts based on installed packages and services.
    """

    __tablename__ = "host_roles"

    id = Column(Integer, primary_key=True)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(100), nullable=False)  # e.g., "Web Server", "Database Server"
    package_name = Column(
        String(255), nullable=False
    )  # e.g., "apache2", "nginx", "postgresql"
    package_version = Column(String(100))  # Version of the main package
    service_name = Column(String(255))  # Name of the associated service
    service_status = Column(String(20))  # "running", "stopped", "unknown"
    is_active = Column(Boolean, default=True)  # Whether the service is currently active
    detected_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to host
    host = relationship("Host", back_populates="roles")

    def __repr__(self):
        return f"<HostRole(host_id={self.host_id}, role={self.role}, package={self.package_name})>"

    def to_dict(self) -> dict:
        """Convert the host role to a dictionary."""
        return {
            "id": self.id,
            "host_id": self.host_id,
            "role": self.role,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "service_name": self.service_name,
            "service_status": self.service_status,
            "is_active": self.is_active,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
