"""
SSH key and certificate deployment endpoints.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import Host
from backend.persistence.models.secret import Secret
from backend.security.roles import SecurityRoles
from backend.services.vault_service import VaultError, VaultService
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    server_queue_manager,
)

from .models import CertificateDeployRequest, SSHKeyDeployRequest
from .permissions import check_user_permission

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/secrets/deploy-ssh-keys", dependencies=[Depends(JWTBearer())])
async def deploy_ssh_keys(
    deploy_request: SSHKeyDeployRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Deploy SSH keys to a user on a target host via agent."""
    try:
        # Check if user has permission to deploy SSH keys
        check_user_permission(current_user, SecurityRoles.DEPLOY_SSH_KEY)

        # Validate host exists and is active
        host = (
            db.query(Host).filter(Host.id == uuid.UUID(deploy_request.host_id)).first()
        )
        if not host:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("hosts.not_found", "Host not found"),
            )

        if not host.active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("hosts.not_active", "Host is not active"),
            )

        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_(
                    "hosts.not_privileged",
                    "Host agent is not running in privileged mode",
                ),
            )

        # Convert string IDs to UUIDs and validate secrets exist
        uuid_ids = []
        for secret_id in deploy_request.secret_ids:
            try:
                uuid_ids.append(uuid.UUID(secret_id))
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=_("secrets.invalid_id", "Invalid secret ID: {id}").format(
                        id=secret_id
                    ),
                ) from exc

        # Get secrets and validate they are SSH keys
        secrets = db.query(Secret).filter(Secret.id.in_(uuid_ids)).all()
        if len(secrets) != len(uuid_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("secrets.some_not_found", "Some secrets not found"),
            )

        ssh_keys = [s for s in secrets if s.secret_type == "ssh_key"]  # nosec B105
        if len(ssh_keys) != len(secrets):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("secrets.not_ssh_keys", "All secrets must be SSH keys"),
            )

        # Retrieve secret contents from vault
        vault_service = VaultService()
        ssh_key_data = []

        for secret in ssh_keys:
            try:
                vault_data = vault_service.retrieve_secret(
                    secret.vault_path, secret.vault_token
                )
                ssh_key_data.append(
                    {
                        "id": str(secret.id),
                        "name": secret.name,
                        "filename": secret.filename
                        or f"id_rsa{'_pub' if secret.secret_subtype == 'public' else ''}",  # nosec B105
                        "content": vault_data.get("content", ""),
                        "subtype": secret.secret_subtype,
                    }
                )
            except VaultError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=_(
                        "secrets.vault_error",
                        "Failed to retrieve secret from vault: {error}",
                    ).format(error=str(e)),
                ) from e

        # Create message data for agent
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        message_data = {
            "command_type": "deploy_ssh_keys",
            "parameters": {
                "username": deploy_request.username,
                "ssh_keys": ssh_key_data,
                "requested_by": current_user,
                "requested_at": now.isoformat(),
            },
        }

        # Queue the message for the agent
        try:
            message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=message_data,
                direction=QueueDirection.OUTBOUND,
                host_id=str(host.id),
                priority=Priority.NORMAL,
                db=None,  # Let queue manager create its own session
            )
        except Exception as e:
            logger.error("Failed to enqueue SSH deployment message: %s", str(e))
            raise

        return {
            "message": _(
                "secrets.ssh_keys_deployment_queued",
                "SSH keys deployment queued successfully",
            ),
            "message_id": message_id,
            "host_id": str(host.id),
            "username": deploy_request.username,
            "key_count": len(ssh_key_data),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("secrets.deploy_ssh_keys_error", "Failed to deploy SSH keys"),
        ) from e


@router.post("/secrets/deploy-certificates", dependencies=[Depends(JWTBearer())])
async def deploy_certificates(
    deploy_request: CertificateDeployRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Deploy SSL certificates to a target host via agent."""
    try:
        # Check if user has permission to deploy certificates
        check_user_permission(current_user, SecurityRoles.DEPLOY_CERTIFICATE)

        # Validate host exists and is active
        host = (
            db.query(Host).filter(Host.id == uuid.UUID(deploy_request.host_id)).first()
        )
        if not host:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("hosts.not_found", "Host not found"),
            )

        if not host.active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("hosts.not_active", "Host is not active"),
            )

        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_(
                    "hosts.not_privileged",
                    "Host agent is not running in privileged mode",
                ),
            )

        # Convert string IDs to UUIDs and validate secrets exist
        uuid_ids = []
        for secret_id in deploy_request.secret_ids:
            try:
                uuid_ids.append(uuid.UUID(secret_id))
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=_("secrets.invalid_id", "Invalid secret ID: {id}").format(
                        id=secret_id
                    ),
                ) from exc

        # Get secrets and validate they are SSL certificates
        secrets = db.query(Secret).filter(Secret.id.in_(uuid_ids)).all()
        if len(secrets) != len(uuid_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("secrets.some_not_found", "Some secrets not found"),
            )

        certificates = [
            s for s in secrets if s.secret_type == "ssl_certificate"  # nosec B105
        ]
        if len(certificates) != len(secrets):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_(
                    "secrets.not_certificates", "All secrets must be SSL certificates"
                ),
            )

        # Retrieve secret contents from vault
        vault_service = VaultService()
        certificate_data = []

        for secret in certificates:
            try:
                vault_data = vault_service.retrieve_secret(
                    secret.vault_path, secret.vault_token
                )
                certificate_data.append(
                    {
                        "id": str(secret.id),
                        "name": secret.name,
                        "filename": secret.filename or f"{secret.name}.crt",
                        "content": vault_data.get("content", ""),
                        "subtype": secret.secret_subtype,
                    }
                )
            except VaultError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=_(
                        "secrets.vault_error",
                        "Failed to retrieve secret from vault: {error}",
                    ).format(error=str(e)),
                ) from e

        # Create message data for agent
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        message_data = {
            "command_type": "deploy_certificates",
            "parameters": {
                "certificates": certificate_data,
                "requested_by": current_user,
                "requested_at": now.isoformat(),
            },
        }

        # Queue the message for the agent
        try:
            message_id = server_queue_manager.enqueue_message(
                message_type="command",
                message_data=message_data,
                direction=QueueDirection.OUTBOUND,
                host_id=str(host.id),
                priority=Priority.NORMAL,
                db=None,  # Let queue manager create its own session
            )
        except Exception as e:
            logger.error("Failed to enqueue certificate deployment message: %s", str(e))
            raise

        return {
            "message": _(
                "secrets.certificates_deployment_queued",
                "Certificates deployment queued successfully",
            ),
            "message_id": message_id,
            "host_id": str(host.id),
            "certificate_count": len(certificate_data),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_(
                "secrets.deploy_certificates_error", "Failed to deploy certificates"
            ),
        ) from e
