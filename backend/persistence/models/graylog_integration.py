"""
Graylog integration settings model for managing Graylog server connections.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class GraylogIntegrationSettings(Base):
    """
    Model to store Graylog integration settings and configuration.
    """

    __tablename__ = "graylog_integration_settings"

    id = Column(GUID(), primary_key=True, default=uuid4)
    enabled = Column(Boolean, default=False, nullable=False)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="SET NULL"), nullable=True)
    manual_url = Column(String(255), nullable=True)
    use_managed_server = Column(Boolean, default=True, nullable=False)
    api_token_vault_token = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Graylog input ports detection
    has_gelf_tcp = Column(Boolean, nullable=True)
    gelf_tcp_port = Column(Integer, nullable=True)
    has_syslog_tcp = Column(Boolean, nullable=True)
    syslog_tcp_port = Column(Integer, nullable=True)
    has_syslog_udp = Column(Boolean, nullable=True)
    syslog_udp_port = Column(Integer, nullable=True)
    has_windows_sidecar = Column(Boolean, nullable=True)
    windows_sidecar_port = Column(Integer, nullable=True)
    inputs_last_checked = Column(DateTime, nullable=True)

    # Relationship to host
    host = relationship("Host", back_populates="graylog_integration")

    def __repr__(self):
        return f"<GraylogIntegrationSettings(id={self.id}, enabled={self.enabled}, host_id={self.host_id})>"

    def to_dict(self) -> dict:
        """Convert the Graylog integration settings to a dictionary."""
        # Build host dict manually if host exists
        host_dict = None
        if self.host:
            host_dict = {
                "id": str(self.host.id),
                "fqdn": self.host.fqdn,
                "ipv4": self.host.ipv4,
                "ipv6": self.host.ipv6,
                "platform": self.host.platform,
                "active": self.host.active,
                "approval_status": self.host.approval_status,
            }

        return {
            "id": str(self.id),
            "enabled": self.enabled,
            "host_id": str(self.host_id) if self.host_id else None,
            "manual_url": self.manual_url,
            "use_managed_server": self.use_managed_server,
            "api_token": (
                "***" if self.api_token_vault_token else None
            ),  # Hide API token for security
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "host": host_dict,
            "has_gelf_tcp": self.has_gelf_tcp,
            "gelf_tcp_port": self.gelf_tcp_port,
            "has_syslog_tcp": self.has_syslog_tcp,
            "syslog_tcp_port": self.syslog_tcp_port,
            "has_syslog_udp": self.has_syslog_udp,
            "syslog_udp_port": self.syslog_udp_port,
            "has_windows_sidecar": self.has_windows_sidecar,
            "windows_sidecar_port": self.windows_sidecar_port,
            "inputs_last_checked": (
                self.inputs_last_checked.isoformat()
                if self.inputs_last_checked
                else None
            ),
        }

    @property
    def graylog_url(self) -> Optional[str]:
        """Get the effective Graylog URL based on configuration."""
        if self.use_managed_server and self.host:
            # Construct URL from managed host (assuming standard Graylog port 9000)
            return f"http://{self.host.fqdn}:9000"  # NOSONAR - Graylog default URL, configurable via manual_url
        elif not self.use_managed_server and self.manual_url:
            return self.manual_url
        return None
