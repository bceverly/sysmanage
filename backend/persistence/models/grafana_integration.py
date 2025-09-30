"""
Grafana integration settings model for managing Grafana server connections.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class GrafanaIntegrationSettings(Base):
    """
    Model to store Grafana integration settings and configuration.
    """

    __tablename__ = "grafana_integration_settings"

    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, default=False, nullable=False)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="SET NULL"), nullable=True)
    manual_url = Column(String(255), nullable=True)
    use_managed_server = Column(Boolean, default=True, nullable=False)
    api_key_vault_token = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship to host
    host = relationship("Host", back_populates="grafana_integration")

    def __repr__(self):
        return f"<GrafanaIntegrationSettings(id={self.id}, enabled={self.enabled}, host_id={self.host_id})>"

    def to_dict(self) -> dict:
        """Convert the Grafana integration settings to a dictionary."""
        return {
            "id": self.id,
            "enabled": self.enabled,
            "host_id": self.host_id,
            "manual_url": self.manual_url,
            "use_managed_server": self.use_managed_server,
            "api_key": (
                "***" if self.api_key_vault_token else None
            ),  # Hide API key for security
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "host": (
                self.host.to_dict()
                if self.host and hasattr(self.host, "to_dict")
                else None
            ),
        }

    @property
    def grafana_url(self) -> Optional[str]:
        """Get the effective Grafana URL based on configuration."""
        if self.use_managed_server and self.host:
            # Construct URL from managed host (assuming standard Grafana port 3000)
            return f"http://{self.host.fqdn}:3000"
        elif not self.use_managed_server and self.manual_url:
            return self.manual_url
        return None
