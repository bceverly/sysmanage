"""
Database model for secrets management.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, text, func
from sqlalchemy.dialects.postgresql import UUID

from backend.persistence.db import Base


class Secret(Base):
    """Model for storing secret metadata (not the actual secret content)."""

    __tablename__ = "secrets"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    name = Column(String(255), nullable=False, index=True)
    secret_type = Column(String(50), nullable=False, index=True)  # 'ssh_key', etc.
    key_visibility = Column(
        String(20), nullable=True
    )  # For SSH keys: 'public' or 'private'
    vault_token = Column(Text, nullable=False)  # Token to retrieve secret from OpenBAO
    vault_path = Column(
        String(500), nullable=False
    )  # Path in vault where secret is stored

    # Audit fields
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    created_by = Column(String(255), nullable=False)  # Username who created the secret
    updated_by = Column(
        String(255), nullable=False
    )  # Username who last updated the secret

    def __repr__(self):
        return f"<Secret(id={self.id}, name='{self.name}', type='{self.secret_type}')>"

    def to_dict(self):
        """Convert to dictionary for API responses (excludes sensitive data)."""
        return {
            "id": str(self.id),
            "name": self.name,
            "secret_type": self.secret_type,
            "key_visibility": self.key_visibility,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }
