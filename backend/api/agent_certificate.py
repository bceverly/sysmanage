# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Agent certificates and the server's identity (ROADMAP 25.10).

``POST /api/agent/certificate`` -- a host sends a certificate request for a
key it generated itself and gets back its client certificate.  The private
key never leaves the host (the older ``/api/certificates/client/{id}``
generated the key here and sent it over the wire, and no agent ever called
it).  The agent authenticates exactly as for ``/api/agent/poll``: its
connection token, and its host token in ``X-Host-Token``.  When certificates
are enforced, a host that holds no unexpired certificate may still get one on
its token -- otherwise a new or expired host could never connect again.

``GET /api/agent/server-identity`` -- unauthenticated, because the content is
signed: this server's CA and identity certificate, and a statement, signed
with the identity key, naming the TLS public keys agents are served now.  An
agent that pinned this server checks it before trusting a renewed TLS
certificate (``backend.security.agent_mtls``).
"""

from typing import Optional

from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.agent_poll import _authenticated_host_id, _host_session, _verify_host
from backend.i18n import _
from backend.persistence.db import get_db
from backend.security import agent_mtls
from backend.security.certificate_manager import certificate_manager
from backend.services.audit_service import ActionType, AuditService, EntityType
from backend.utils.log_sanitize import scrub
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.agent_certificate")

router = APIRouter()

NO_STORE = {"Cache-Control": "no-store"}


class CertificateRequest(BaseModel):
    host_id: str = Field(min_length=1, max_length=64)
    csr: str = Field(min_length=1, max_length=16384)


def _refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _current_not_presented(host, request: Request) -> bool:
    """Enforced mode, and the host's still-valid certificate was not shown."""
    if agent_mtls.mode_for_host(str(host.id)) != agent_mtls.MODE_ENFORCED:
        return False
    if not agent_mtls.has_current_certificate(host):
        return False
    presented = agent_mtls.presented_certificate(
        request.headers.get(agent_mtls.CLIENT_CERT_HEADER)
    )
    return agent_mtls.verdict_for(presented, host) != agent_mtls.VALID


@router.post("/agent/certificate")
async def agent_certificate(
    request: Request,
    payload: CertificateRequest,
    authorization: Optional[str] = Header(default=None),
    x_host_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Sign this host's certificate request."""
    host_id = _authenticated_host_id(request, payload, authorization)
    host_db = _host_session(host_id, db)
    try:
        host = _verify_host(
            host_db, host_id, x_host_token, request, certificate_bootstrap=True
        )
        if host.approval_status != "approved":
            raise _refuse(403, "host_not_approved", _("This host is not approved yet"))
        if _current_not_presented(host, request):
            raise _refuse(
                409,
                "certificate_current",
                _(
                    "This host already has a valid certificate; present it to "
                    "renew, or wait until it is close to expiry"
                ),
            )
        try:
            cert = agent_mtls.issue_from_csr(host, payload.csr)
        except agent_mtls.CsrRefused as refused:
            raise _refuse(400, "csr_invalid", str(refused)) from refused
        AuditService.log(
            db=host_db,
            user_id=None,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description="Client certificate issued to the host from its request",
            details={
                "serial": str(cert.serial_number),
                "not_after": cert.not_valid_after_utc.isoformat(),
            },
            commit=False,
        )
        host_db.commit()
        logger.info("Issued a client certificate to host %s", scrub(host_id))
    finally:
        if host_db is not db:
            host_db.close()
    not_after = cert.not_valid_after_utc
    return JSONResponse(
        {
            "certificate": cert.public_bytes(serialization.Encoding.PEM).decode(),
            "ca_certificate": certificate_manager.get_ca_certificate().decode(),
            "not_after": not_after.isoformat(),
            "renew_after": (not_after - agent_mtls.RENEW_BEFORE).isoformat(),
        },
        headers=NO_STORE,
    )


@router.get("/agent/server-identity")
async def agent_server_identity() -> JSONResponse:
    """This server's signed statement of the TLS keys it serves."""
    spki = agent_mtls.served_tls_spki()
    if not spki:
        raise _refuse(
            503,
            "tls_identity_unknown",
            _(
                "This server could not read the TLS certificate it serves to "
                "agents. Set agent_tls_spki in Settings, or check that nginx "
                "answers on this host."
            ),
        )
    return JSONResponse(agent_mtls.identity_document(spki), headers=NO_STORE)
