"""
SSH key and certificate deployment endpoints.

NOTE: Secrets deployment is a Pro+ feature. The actual implementation
is provided by the secrets_engine module. This file provides stub
endpoints that return license-required errors for community users.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence.db import get_db

from .models import CertificateDeployRequest, SSHKeyDeployRequest

router = APIRouter()
logger = logging.getLogger(__name__)


def _check_secrets_module():
    """Check if secrets_engine Pro+ module is available."""
    secrets_engine = module_loader.get_module("secrets_engine")
    if secrets_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Secrets deployment requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )
    return secrets_engine


@router.post("/secrets/deploy-ssh-keys", dependencies=[Depends(JWTBearer())])
async def deploy_ssh_keys(
    deploy_request: SSHKeyDeployRequest,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Deploy SSH keys to a user on a target host via agent.

    This is a Pro+ feature. Requires secrets_engine module.
    """
    _check_secrets_module()
    raise HTTPException(
        status_code=307,
        detail=_("Use /api/v1/secrets/deploy-ssh-keys with Pro+ license"),
        headers={"Location": "/api/v1/secrets/deploy-ssh-keys"},
    )


@router.post("/secrets/deploy-certificates", dependencies=[Depends(JWTBearer())])
async def deploy_certificates(
    deploy_request: CertificateDeployRequest,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Deploy SSL certificates to a target host via agent.

    This is a Pro+ feature. Requires secrets_engine module.
    """
    _check_secrets_module()
    raise HTTPException(
        status_code=307,
        detail=_("Use /api/v1/secrets/deploy-certificates with Pro+ license"),
        headers={"Location": "/api/v1/secrets/deploy-certificates"},
    )
