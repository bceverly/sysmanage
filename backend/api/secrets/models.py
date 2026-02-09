"""
Pydantic models for secrets API.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class SecretCreate(BaseModel):
    """Model for creating a new secret."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Name of the secret"
    )
    filename: Optional[str] = Field(
        None,
        max_length=255,
        description="Filename for the secret (e.g., id_rsa.pub, server.crt)",
    )
    secret_type: str = Field(..., description="Type of secret (e.g., 'ssh_key')")
    content: str = Field(..., min_length=1, description="The secret content")
    secret_subtype: Optional[str] = Field(
        None,
        description="For SSH keys: 'public', 'private', 'ca' | For SSL certificates: 'root', 'intermediate', 'chain', 'key_file', 'certificate' | For Database credentials: 'postgresql', 'mysql', 'oracle', 'sqlserver', 'sqlite' | For API keys: 'github', 'salesforce'",
    )


class SecretUpdate(BaseModel):
    """Model for updating an existing secret."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Name of the secret"
    )
    filename: Optional[str] = Field(
        None,
        max_length=255,
        description="Filename for the secret (e.g., id_rsa.pub, server.crt)",
    )
    content: Optional[str] = Field(None, min_length=1, description="The secret content")
    secret_subtype: Optional[str] = Field(
        None,
        description="For SSH keys: 'public', 'private', 'ca' | For SSL certificates: 'root', 'intermediate', 'chain', 'key_file', 'certificate' | For Database credentials: 'postgresql', 'mysql', 'oracle', 'sqlserver', 'sqlite' | For API keys: 'github', 'salesforce'",
    )


class SecretResponse(BaseModel):
    """Model for secret responses (without content)."""

    id: str
    name: str
    filename: Optional[str] = None
    secret_type: str
    secret_subtype: Optional[str] = None
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str


class SecretWithContent(SecretResponse):
    """Model for secret responses with content (for viewing)."""

    content: str


class SSHKeyDeployRequest(BaseModel):
    """Model for SSH key deployment request."""

    host_id: str = Field(..., description="Target host ID")
    username: str = Field(..., description="Target username")
    secret_ids: List[str] = Field(
        ..., min_items=1, description="List of secret IDs to deploy"
    )


class CertificateDeployRequest(BaseModel):
    """Model for certificate deployment request."""

    host_id: str = Field(..., description="Target host ID")
    secret_ids: List[str] = Field(
        ..., min_items=1, description="List of certificate secret IDs to deploy"
    )
