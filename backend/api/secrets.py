"""
API endpoints for secrets management.
"""

import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.persistence.db import get_db
from backend.persistence.models.secret import Secret
from backend.services.vault_service import VaultService, VaultError
from backend.i18n import _

router = APIRouter()


class SecretCreate(BaseModel):
    """Model for creating a new secret."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Name of the secret"
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
    content: Optional[str] = Field(None, min_length=1, description="The secret content")
    secret_subtype: Optional[str] = Field(
        None,
        description="For SSH keys: 'public', 'private', 'ca' | For SSL certificates: 'root', 'intermediate', 'chain', 'key_file', 'certificate' | For Database credentials: 'postgresql', 'mysql', 'oracle', 'sqlserver', 'sqlite' | For API keys: 'github', 'salesforce'",
    )


class SecretResponse(BaseModel):
    """Model for secret responses (without content)."""

    id: str
    name: str
    secret_type: str
    secret_subtype: Optional[str]
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str


class SecretWithContent(SecretResponse):
    """Model for secret responses with content (for viewing)."""

    content: str


@router.get(
    "/secrets", response_model=List[SecretResponse], dependencies=[Depends(JWTBearer())]
)
async def list_secrets(
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """List all secrets (metadata only, no content)."""
    try:
        secrets = db.query(Secret).order_by(Secret.created_at.desc()).all()
        return [SecretResponse(**secret.to_dict()) for secret in secrets]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("secrets.list_error", "Failed to retrieve secrets"),
        ) from e


@router.get("/secrets/types", dependencies=[Depends(JWTBearer())])
async def get_secret_types():
    """Get available secret types."""
    return {
        "types": [
            {
                "value": "api_keys",
                "label": _("secrets.type.api_keys", "API Keys"),
                "supports_visibility": True,
                "visibility_label": _("secrets.apiProvider", "API Provider"),
                "visibility_options": [
                    {
                        "value": "github",
                        "label": _("secrets.api_provider.github", "Github"),
                    },
                    {
                        "value": "salesforce",
                        "label": _("secrets.api_provider.salesforce", "Salesforce"),
                    },
                ],
            },
            {
                "value": "database_credentials",
                "label": _("secrets.type.database_credentials", "Database Credentials"),
                "supports_visibility": True,
                "visibility_label": _("secrets.databaseEngine", "Database Engine"),
                "visibility_options": [
                    {
                        "value": "mysql",
                        "label": _("secrets.database_engine.mysql", "mysql"),
                    },
                    {
                        "value": "oracle",
                        "label": _("secrets.database_engine.oracle", "Oracle"),
                    },
                    {
                        "value": "postgresql",
                        "label": _("secrets.database_engine.postgresql", "PostgreSQL"),
                    },
                    {
                        "value": "sqlserver",
                        "label": _(
                            "secrets.database_engine.sqlserver", "Microsoft SQL Server"
                        ),
                    },
                    {
                        "value": "sqlite",
                        "label": _("secrets.database_engine.sqlite", "sqlite3"),
                    },
                ],
            },
            {
                "value": "ssh_key",
                "label": _("secrets.type.ssh_key", "SSH Key"),
                "supports_visibility": True,
                "visibility_label": _("secrets.keyType", "Key Type"),
                "visibility_options": [
                    {
                        "value": "public",
                        "label": _("secrets.key_type.public", "Public"),
                    },
                    {
                        "value": "private",
                        "label": _("secrets.key_type.private", "Private"),
                    },
                    {
                        "value": "ca",
                        "label": _("secrets.key_type.ca", "CA"),
                    },
                ],
            },
            {
                "value": "ssl_certificate",
                "label": _("secrets.type.ssl_certificate", "SSL Certificate"),
                "supports_visibility": True,
                "visibility_label": _("secrets.certificateType", "Certificate Type"),
                "visibility_options": [
                    {
                        "value": "root",
                        "label": _("secrets.certificate_type.root", "Root Certificate"),
                    },
                    {
                        "value": "intermediate",
                        "label": _(
                            "secrets.certificate_type.intermediate",
                            "Intermediate Certificate",
                        ),
                    },
                    {
                        "value": "chain",
                        "label": _(
                            "secrets.certificate_type.chain", "Chain Certificate"
                        ),
                    },
                    {
                        "value": "key_file",
                        "label": _("secrets.certificate_type.key_file", "Key File"),
                    },
                    {
                        "value": "certificate",
                        "label": _(
                            "secrets.certificate_type.certificate", "Issued Certificate"
                        ),
                    },
                ],
            },
        ]
    }


@router.get(
    "/secrets/{secret_id}",
    response_model=SecretResponse,
    dependencies=[Depends(JWTBearer())],
)
async def get_secret_metadata(
    secret_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get secret metadata (without content)."""
    try:
        secret = db.query(Secret).filter(Secret.id == uuid.UUID(secret_id)).first()
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("secrets.not_found", "Secret not found"),
            )
        return SecretResponse(**secret.to_dict())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("secrets.invalid_id", "Invalid secret ID"),
        ) from exc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("secrets.get_error", "Failed to retrieve secret"),
        ) from e


@router.get(
    "/secrets/{secret_id}/content",
    response_model=SecretWithContent,
    dependencies=[Depends(JWTBearer())],
)
async def get_secret_content(
    secret_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get secret with content from vault."""
    try:
        secret = db.query(Secret).filter(Secret.id == uuid.UUID(secret_id)).first()
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("secrets.not_found", "Secret not found"),
            )

        # Retrieve content from vault
        vault_service = VaultService()
        try:
            vault_data = vault_service.retrieve_secret(
                secret.vault_path, secret.vault_token
            )
            content = vault_data.get("content", "")
        except VaultError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_(
                    "secrets.vault_error",
                    "Failed to retrieve secret from vault: {error}",
                ).format(error=str(e)),
            ) from e

        # Return secret with content
        secret_dict = secret.to_dict()
        secret_dict["content"] = content
        return SecretWithContent(**secret_dict)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("secrets.invalid_id", "Invalid secret ID"),
        ) from exc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("secrets.get_content_error", "Failed to retrieve secret content"),
        ) from e


@router.post(
    "/secrets", response_model=SecretResponse, dependencies=[Depends(JWTBearer())]
)
async def create_secret(
    secret_data: SecretCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new secret."""
    try:
        # Check if secret name already exists
        existing = db.query(Secret).filter(Secret.name == secret_data.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("secrets.name_exists", "Secret with this name already exists"),
            )

        # Store secret in vault
        vault_service = VaultService()
        try:
            vault_info = vault_service.store_secret(
                secret_data.name,
                secret_data.content,
                secret_data.secret_type,
                secret_data.secret_subtype,
            )
        except VaultError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_(
                    "secrets.vault_store_error",
                    "Failed to store secret in vault: {error}",
                ).format(error=str(e)),
            ) from e

        # Create database record
        secret = Secret(
            name=secret_data.name,
            secret_type=secret_data.secret_type,
            secret_subtype=secret_data.secret_subtype,
            vault_token=vault_info["vault_token"],
            vault_path=vault_info["vault_path"],
            created_by=current_user,
            updated_by=current_user,
        )

        db.add(secret)
        db.commit()
        db.refresh(secret)

        return SecretResponse(**secret.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("secrets.create_error", "Failed to create secret"),
        ) from e


@router.put(
    "/secrets/{secret_id}",
    response_model=SecretResponse,
    dependencies=[Depends(JWTBearer())],
)
async def update_secret(
    secret_id: str,
    secret_data: SecretUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update an existing secret."""
    try:
        secret = db.query(Secret).filter(Secret.id == uuid.UUID(secret_id)).first()
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("secrets.not_found", "Secret not found"),
            )

        # Check if new name conflicts with existing secrets
        if secret_data.name and secret_data.name != secret.name:
            existing = (
                db.query(Secret)
                .filter(Secret.name == secret_data.name, Secret.id != secret.id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=_(
                        "secrets.name_exists", "Secret with this name already exists"
                    ),
                )

        # If content is being updated, update in vault
        if secret_data.content:
            vault_service = VaultService()
            try:
                # Delete old secret
                vault_service.delete_secret(secret.vault_path, secret.vault_token)

                # Store new secret
                vault_info = vault_service.store_secret(
                    secret_data.name or secret.name,
                    secret_data.content,
                    secret.secret_type,
                    secret_data.secret_subtype or secret.secret_subtype,
                )

                # Update vault references
                secret.vault_token = vault_info["vault_token"]
                secret.vault_path = vault_info["vault_path"]
            except VaultError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=_(
                        "secrets.vault_update_error",
                        "Failed to update secret in vault: {error}",
                    ).format(error=str(e)),
                ) from e

        # Update database record
        if secret_data.name:
            secret.name = secret_data.name
        if secret_data.secret_subtype is not None:
            secret.secret_subtype = secret_data.secret_subtype

        secret.updated_by = current_user

        db.commit()
        db.refresh(secret)

        return SecretResponse(**secret.to_dict())

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("secrets.invalid_id", "Invalid secret ID"),
        ) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("secrets.update_error", "Failed to update secret"),
        ) from e


@router.delete("/secrets/{secret_id}", dependencies=[Depends(JWTBearer())])
async def delete_secret(
    secret_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a secret."""
    try:
        secret = db.query(Secret).filter(Secret.id == uuid.UUID(secret_id)).first()
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("secrets.not_found", "Secret not found"),
            )

        # Delete from vault
        vault_service = VaultService()
        try:
            vault_service.delete_secret(secret.vault_path, secret.vault_token)
        except VaultError as e:
            # Log warning but continue with database deletion
            # In production, you might want to mark as "pending deletion" instead
            print(f"VAULT DELETE ERROR: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_(
                    "secrets.vault_delete_error",
                    "Failed to delete secret from vault: {error}",
                ).format(error=str(e)),
            ) from e

        # Delete from database
        db.delete(secret)
        db.commit()

        return {"message": _("secrets.deleted", "Secret deleted successfully")}

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("secrets.invalid_id", "Invalid secret ID"),
        ) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("secrets.delete_error", "Failed to delete secret"),
        ) from e


@router.delete("/secrets", dependencies=[Depends(JWTBearer())])
async def delete_multiple_secrets(
    secret_ids: List[str],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete multiple secrets."""
    if not secret_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("secrets.no_ids", "No secret IDs provided"),
        )

    try:
        # Convert string IDs to UUIDs
        uuid_ids = []
        for secret_id in secret_ids:
            try:
                uuid_ids.append(uuid.UUID(secret_id))
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=_("secrets.invalid_id", "Invalid secret ID: {id}").format(
                        id=secret_id
                    ),
                ) from exc

        # Get all secrets to delete
        secrets = db.query(Secret).filter(Secret.id.in_(uuid_ids)).all()
        if len(secrets) != len(uuid_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("secrets.some_not_found", "Some secrets not found"),
            )

        # Delete from vault
        vault_service = VaultService()
        vault_errors = []
        for secret in secrets:
            try:
                vault_service.delete_secret(secret.vault_path, secret.vault_token)
            except VaultError as e:
                vault_errors.append(f"{secret.name}: {str(e)}")

        # Delete from database
        for secret in secrets:
            db.delete(secret)

        db.commit()

        result = {
            "message": _("secrets.deleted_multiple", "Secrets deleted successfully")
        }
        if vault_errors:
            result["vault_warnings"] = vault_errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("secrets.delete_multiple_error", "Failed to delete secrets"),
        ) from e
