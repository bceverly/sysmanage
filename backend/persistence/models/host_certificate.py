"""
Database model for host SSL certificates.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.persistence.db import Base


class HostCertificate(Base):
    """Model for storing SSL certificate information from hosts."""

    __tablename__ = "host_certificates"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    host_id = Column(
        UUID(as_uuid=True), ForeignKey("host.id", ondelete="CASCADE"), nullable=False
    )
    file_path = Column(
        String(1000), nullable=False, index=True
    )  # Full path + filename of the certificate file
    certificate_name = Column(
        String(500), nullable=True
    )  # Human-readable name extracted from certificate
    subject = Column(Text, nullable=True)  # Certificate subject (CN, O, OU, etc.)
    issuer = Column(Text, nullable=True)  # Certificate issuer information
    not_before = Column(DateTime, nullable=True)  # Certificate valid from date
    not_after = Column(
        DateTime, nullable=True, index=True
    )  # Certificate expiration date
    serial_number = Column(String(100), nullable=True)  # Certificate serial number
    fingerprint_sha256 = Column(
        String(64), nullable=True, index=True
    )  # SHA256 fingerprint for uniqueness
    is_ca = Column(Boolean, nullable=True)  # Is this a CA certificate
    key_usage = Column(
        String(500), nullable=True
    )  # Key usage extensions (e.g., "Digital Signature, Key Encipherment")

    # Audit and tracking fields
    collected_at = Column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
        index=True,
    )  # When this certificate data was collected from the host
    created_at = Column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    # Relationship to host
    host = relationship("Host", back_populates="certificates")

    def __repr__(self):
        return f"<HostCertificate(id={self.id}, host_id={self.host_id}, path='{self.file_path}', expires={self.not_after})>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "host_id": str(self.host_id),
            "file_path": self.file_path,
            "certificate_name": self.certificate_name,
            "subject": self.subject,
            "issuer": self.issuer,
            "not_before": self.not_before.isoformat() if self.not_before else None,
            "not_after": self.not_after.isoformat() if self.not_after else None,
            "serial_number": self.serial_number,
            "fingerprint_sha256": self.fingerprint_sha256,
            "is_ca": self.is_ca,
            "key_usage": self.key_usage,
            "collected_at": (
                self.collected_at.isoformat() if self.collected_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def is_expired(self) -> bool:
        """Check if the certificate is expired."""
        if not self.not_after:
            return False
        return datetime.now(self.not_after.tzinfo) > self.not_after

    @property
    def days_until_expiry(self) -> int:
        """Get days until certificate expires (negative if already expired)."""
        if not self.not_after:
            return 0
        delta = self.not_after - datetime.now(self.not_after.tzinfo)
        return delta.days

    @property
    def common_name(self) -> str:
        """Extract common name from subject."""
        if not self.subject:
            return ""
        # Parse subject string to extract CN
        for part in self.subject.split(","):
            part = part.strip()
            if part.startswith("CN="):
                return part[3:]  # Remove "CN=" prefix
        return ""
