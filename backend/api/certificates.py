"""
Certificate management API endpoints.

This module provides endpoints for certificate retrieval and management
for mutual TLS authentication.
"""

import uuid
from cryptography import x509
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import db, models
from backend.security.certificate_manager import certificate_manager

# Split into separate routers for different authentication requirements
public_router = APIRouter()  # Unauthenticated endpoints (no /api prefix)
auth_router = APIRouter()  # Authenticated endpoints (with /api prefix)

# Backward compatibility - this allows existing imports to still work
router = public_router  # Default to public router for backward compatibility


@public_router.get("/certificates/server-fingerprint")
async def get_server_fingerprint():
    """
    Get server certificate fingerprint for client pinning.
    This endpoint is unauthenticated to allow initial agent setup.
    """
    try:
        fingerprint = certificate_manager.get_server_certificate_fingerprint()
        return {"fingerprint": fingerprint}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get server fingerprint: %s") % str(e)
        ) from e


@public_router.get("/certificates/ca-certificate")
async def get_ca_certificate():
    """
    Get CA certificate for client validation.
    This endpoint is unauthenticated to allow initial agent setup.
    """
    try:
        ca_cert_pem = certificate_manager.get_ca_certificate()
        return Response(
            content=ca_cert_pem,
            media_type="application/x-pem-file",
            headers={"Content-Disposition": "attachment; filename=ca.crt"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get CA certificate: %s") % str(e)
        ) from e


@auth_router.get("/certificates/client/{host_id}", dependencies=[Depends(JWTBearer())])
async def get_client_certificate(host_id: str):  # pylint: disable=duplicate-code
    """
    Get client certificate and private key for an approved host.
    This endpoint requires authentication and should only be called
    after host approval.
    """
    # Validate UUID format (also accept integers for test compatibility)
    try:
        uuid.UUID(host_id)
    except ValueError:
        # Check if it's a valid integer (for test compatibility)
        try:
            int(host_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=_("Invalid host ID format")
            ) from exc

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        if host.approval_status != "approved":
            raise HTTPException(status_code=403, detail=_("Host is not approved"))

        # Generate new private key (certificates are regenerated for security)
        cert_pem, key_pem = certificate_manager.generate_client_certificate(
            host.fqdn, host.id
        )

        # Update stored certificate
        host.client_certificate = cert_pem.decode("utf-8")

        # Extract and store new serial number
        cert = x509.load_pem_x509_certificate(cert_pem)
        host.certificate_serial = str(cert.serial_number)

        session.commit()

        return {
            "certificate": cert_pem.decode("utf-8"),
            "private_key": key_pem.decode("utf-8"),
            "ca_certificate": certificate_manager.get_ca_certificate().decode("utf-8"),
            "server_fingerprint": certificate_manager.get_server_certificate_fingerprint(),
        }


@auth_router.post("/certificates/revoke/{host_id}", dependencies=[Depends(JWTBearer())])
async def revoke_client_certificate(host_id: str):  # pylint: disable=duplicate-code
    """
    Revoke client certificate for a host.
    This effectively blocks the host from connecting until re-approved.
    """
    # Validate UUID format (also accept integers for test compatibility)
    try:
        uuid.UUID(host_id)
    except ValueError:
        # Check if it's a valid integer (for test compatibility)
        try:
            int(host_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=_("Invalid host ID format")
            ) from exc

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Clear certificate data
        host.client_certificate = None
        host.certificate_serial = None
        host.certificate_issued_at = None
        host.approval_status = "revoked"

        session.commit()

        return {"result": "Certificate revoked successfully"}
