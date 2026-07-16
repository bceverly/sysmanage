# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Federation identity-key endpoints (Settings → Server Role helpers).

Mirror of the air-gap key surface, for the federation trust loop:

  * Expose THIS server's federation *public* identity key + fingerprint so
    the operator can copy it and paste it into the peer (coordinator ⇄
    site).  The private key never leaves the box.
  * Import / list / remove trusted *peer* public keys (the keyring the
    other box's key is pasted into).

Always-mounted OSS routes (you set a federation role + exchange keys BEFORE
the Pro+ engine is licensed/loaded).  The paths (``/identity-key``,
``/trusted-peers``) don't collide with the engine's federation routes.
All routes require a logged-in user.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.services import federation_identity_service

logger = logging.getLogger(__name__)


def federation_request(request: Request) -> Request:
    """Pure-Python FastAPI dependency that simply returns the live Request.

    The Pro+ federation engines are Cython-compiled, and FastAPI CANNOT
    introspect special parameters declared inside a compiled module — a
    ``request: Request`` parameter is mis-read as a required ``query.request``
    (HTTP 422), and a ``Header()`` default fails route registration outright
    ("Expected str, got Header").  ``Depends(...)`` markers DO work, so the
    engines depend on this interpreted helper to obtain the Request and then
    read the Authorization / ``X-Federation-Signature`` headers and the raw
    body off it.  Keep it dependency-injectable from the engines.
    """
    return request


router = APIRouter(
    prefix="/api/v1/federation",
    tags=["federation-identity"],
    dependencies=[Depends(JWTBearer())],
)

# A second router WITHOUT the JWT gate: the federation TLS certificate is
# public material (it's exactly what a TLS peer sees in a handshake), and an
# enrolling *site* must fetch the coordinator's cert to pin it BEFORE it has
# any coordinator credentials.  Same prefix, distinct path — no collision.
public_router = APIRouter(
    prefix="/api/v1/federation",
    tags=["federation-identity"],
)


class TlsCertResponse(BaseModel):
    cert_pem: str
    # Phase 12 strict trust: an Ed25519 signature, made with this server's
    # IDENTITY private key, over the fingerprint of the cert above (role-bound).
    # The enrolling site verifies it against the coordinator identity key it was
    # given OUT OF BAND before pinning ``cert_pem`` — so a MITM that swaps the
    # cert here can't forge a matching proof.  ``identity_fingerprint`` lets the
    # operator eyeball-match the key out of band.
    identity_proof: str | None = None
    identity_fingerprint: str | None = None
    identity_role: str | None = None


@public_router.get("/tls-cert", response_model=TlsCertResponse)
def get_tls_cert():
    """Return this server's federation TLS certificate (public, unauthenticated).

    Auto-creates it on first read.  An enrolling site GETs this from its
    coordinator to pin the coordinator's cert for the mutual-TLS handshake,
    and uses ``identity_proof`` to authenticate that cert against the
    out-of-band coordinator identity key before trusting it.
    """
    pem = federation_identity_service.get_federation_tls_cert_pem()
    if not pem:
        raise HTTPException(
            status_code=500,
            detail=_("Could not load or generate the federation TLS certificate."),
        )
    # Sign the proof with whatever federation role this server is configured as
    # (the verifier checks the role it expects, e.g. a site expects
    # "coordinator").  Defaults to "coordinator" so a server that serves this
    # endpoint to enrolling sites produces a verifiable proof even before its
    # role row is populated.
    from backend.config import config as config_module  # noqa: PLC0415

    role = config_module.get_federation_role() or "coordinator"
    if role not in ("coordinator", "site"):
        role = "coordinator"
    return TlsCertResponse(
        cert_pem=pem,
        identity_proof=federation_identity_service.build_enrollment_proof(
            role=role, tls_cert_pem=pem
        ),
        identity_fingerprint=(
            federation_identity_service.get_federation_identity_public_key_fingerprint()
        ),
        identity_role=role,
    )


class IdentityKeyResponse(BaseModel):
    public_key_pem: str
    fingerprint: str


class TrustedPeer(BaseModel):
    name: str
    fingerprint: str | None = None


class TrustedPeerList(BaseModel):
    trusted: list[TrustedPeer]


class ImportTrustedPeer(BaseModel):
    name: str
    public_key_pem: str


@router.get("/identity-key", response_model=IdentityKeyResponse)
def get_identity_key():
    """Return this server's federation public identity key + fingerprint.

    Auto-creates the keypair on first read, so this is available as soon as
    the server is up — the operator copies it to hand to the peer.
    """
    pem = federation_identity_service.get_federation_identity_public_key_pem()
    fingerprint = (
        federation_identity_service.get_federation_identity_public_key_fingerprint()
    )
    if not pem or not fingerprint:
        raise HTTPException(
            status_code=500,
            detail=_("Could not load or generate the federation identity key."),
        )
    return IdentityKeyResponse(public_key_pem=pem, fingerprint=fingerprint)


@router.get("/trusted-peers", response_model=TrustedPeerList)
def list_trusted_peers():
    """List the trusted federation peer keys."""
    rows = federation_identity_service.list_federation_peers()
    return TrustedPeerList(trusted=[TrustedPeer(**row) for row in rows])


@router.post("/trusted-peers", response_model=TrustedPeer)
def import_trusted_peer(payload: ImportTrustedPeer):
    """Import a peer's federation public key into the trusted keyring."""
    try:
        result = federation_identity_service.import_federation_peer(
            payload.name, payload.public_key_pem
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid public key: %s") % str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=_("Could not write key to keyring: %s") % str(exc),
        ) from exc
    return TrustedPeer(**result)


@router.delete("/trusted-peers/{name}", status_code=204)
def remove_trusted_peer(name: str):
    """Remove a trusted peer key by name."""
    if not federation_identity_service.remove_federation_peer(name):
        raise HTTPException(status_code=404, detail=_("Trusted key not found"))
