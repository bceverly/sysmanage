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
    filename = Column(
        String(255), nullable=True
    )  # Filename for the secret (e.g., id_rsa.pub, server.crt)
    secret_type = Column(
        String(50), nullable=False, index=True
    )  # 'ssh_key', 'ssl_certificate', 'database_credentials', 'api_keys', etc.
    secret_subtype = Column(
        String(30), nullable=True
    )  # SSH keys: 'public', 'private', 'ca' | SSL certificates: 'root', 'intermediate', 'chain', 'key_file', 'certificate' | Database credentials: 'postgresql', 'mysql', 'oracle', 'sqlserver', 'sqlite' | API keys: 'github', 'salesforce'
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
            "filename": self.filename,
            "secret_type": self.secret_type,
            "secret_subtype": self.secret_subtype,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }
