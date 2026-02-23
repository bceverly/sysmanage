"""
CRUD endpoints for secrets management.

These endpoints handle basic Create, Read, Update, Delete operations
for secrets, using the database for metadata and OpenBAO vault for
secret content storage.

NOTE: Secrets management is a Pro+ feature. When the secrets_engine module
is not available, list operations return unlicensed responses and all
other operations return 402 errors.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence.db import get_db
from backend.persistence.models.secret import Secret
from backend.services.vault_service import VaultError, VaultService

from .models import SecretCreate, SecretResponse, SecretUpdate, SecretWithContent

router = APIRouter()
logger = logging.getLogger(__name__)

_SECRET_NOT_FOUND = _("Secret not found")
_VAULT_UNAVAILABLE_SUFFIX = " - vault service may not be running"


def _check_secrets_module():
    """Check if secrets_engine Pro+ module is available."""
    secrets_engine = module_loader.get_module("secrets_engine")
    if secrets_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Secrets management requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )
    return secrets_engine


@router.get("/secrets", dependencies=[Depends(JWTBearer())])
async def list_secrets(
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """List all secrets (metadata only, no content)."""
    secrets_engine = module_loader.get_module("secrets_engine")
    if secrets_engine is None:
        return {"licensed": False, "secrets": []}
    secrets = db.query(Secret).order_by(Secret.created_at.desc()).all()
    return [s.to_dict() for s in secrets]


@router.get(
    "/secrets/ssh-keys",
    response_model=List[SecretResponse],
    dependencies=[Depends(JWTBearer())],
)
async def list_ssh_keys(
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """List SSH key secrets."""
    _check_secrets_module()
    secrets = (
        db.query(Secret)
        .filter(
            Secret.secret_type == "ssh_key"
        )  # nosec B105  # secret type filter, not a password
        .order_by(Secret.created_at.desc())
        .all()
    )
    return [s.to_dict() for s in secrets]


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
    _check_secrets_module()
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail=_SECRET_NOT_FOUND)
    return secret.to_dict()


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
    _check_secrets_module()
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail=_SECRET_NOT_FOUND)

    try:
        vault = VaultService()
        vault_data = vault.retrieve_secret(secret.vault_path, secret.vault_token)
        content = vault_data.get("content", "")
    except VaultError as e:
        logger.error("Failed to retrieve secret content from vault: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail=_("Failed to retrieve secret content from vault")
            + _VAULT_UNAVAILABLE_SUFFIX,
        ) from e

    result = secret.to_dict()
    result["content"] = content
    return result


@router.post(
    "/secrets", response_model=SecretResponse, dependencies=[Depends(JWTBearer())]
)
async def create_secret(
    secret_data: SecretCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new secret."""
    _check_secrets_module()

    try:
        vault = VaultService()
        vault_result = vault.store_secret(
            secret_name=secret_data.name,
            secret_data=secret_data.content,
            secret_type=secret_data.secret_type,
            secret_subtype=secret_data.secret_subtype,
        )
    except VaultError as e:
        logger.error("Failed to store secret in vault: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail=_("Failed to store secret in vault") + _VAULT_UNAVAILABLE_SUFFIX,
        ) from e

    username = current_user
    secret = Secret(
        name=secret_data.name,
        filename=secret_data.filename,
        secret_type=secret_data.secret_type,
        secret_subtype=secret_data.secret_subtype,
        vault_path=vault_result["vault_path"],
        vault_token=vault_result["vault_token"],
        created_by=username,
        updated_by=username,
    )
    db.add(secret)
    db.commit()
    db.refresh(secret)
    return secret.to_dict()


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
    _check_secrets_module()

    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail=_SECRET_NOT_FOUND)

    # If new content is provided, store it in vault
    if secret_data.content:
        try:
            vault = VaultService()
            # Delete old vault entry
            try:
                vault.delete_secret(secret.vault_path, secret.vault_token)
            except VaultError:
                logger.warning("Could not delete old vault entry during update")

            # Store new content
            vault_result = vault.store_secret(
                secret_name=secret_data.name or secret.name,
                secret_data=secret_data.content,
                secret_type=secret.secret_type,
                secret_subtype=secret_data.secret_subtype or secret.secret_subtype,
            )
            secret.vault_path = vault_result["vault_path"]
            secret.vault_token = vault_result["vault_token"]
        except VaultError as e:
            logger.error("Failed to update secret in vault: %s", str(e))
            raise HTTPException(
                status_code=503,
                detail=_("Failed to update secret in vault")
                + _VAULT_UNAVAILABLE_SUFFIX,
            ) from e

    # Update metadata fields
    if secret_data.name is not None:
        secret.name = secret_data.name
    if secret_data.filename is not None:
        secret.filename = secret_data.filename
    if secret_data.secret_subtype is not None:
        secret.secret_subtype = secret_data.secret_subtype

    secret.updated_by = current_user
    db.commit()
    db.refresh(secret)
    return secret.to_dict()


@router.delete("/secrets/{secret_id}", dependencies=[Depends(JWTBearer())])
async def delete_secret(
    secret_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a secret."""
    _check_secrets_module()

    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail=_SECRET_NOT_FOUND)

    # Delete from vault
    try:
        vault = VaultService()
        vault.delete_secret(secret.vault_path, secret.vault_token)
    except VaultError as e:
        logger.warning("Failed to delete secret from vault: %s", str(e))
        # Continue with DB deletion even if vault deletion fails

    db.delete(secret)
    db.commit()
    return {"message": _("Secret deleted successfully")}


@router.delete("/secrets", dependencies=[Depends(JWTBearer())])
async def delete_multiple_secrets(
    secret_ids: List[str],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete multiple secrets."""
    _check_secrets_module()

    vault = VaultService()
    deleted_count = 0
    for secret_id in secret_ids:
        secret = db.query(Secret).filter(Secret.id == secret_id).first()
        if secret:
            try:
                vault.delete_secret(secret.vault_path, secret.vault_token)
            except VaultError as e:
                logger.warning(
                    "Failed to delete secret %s from vault: %s", secret_id, str(e)
                )
            db.delete(secret)
            deleted_count += 1

    db.commit()
    return {"message": _("Deleted {count} secrets").format(count=deleted_count)}
