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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.services import federation_identity_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/federation",
    tags=["federation-identity"],
    dependencies=[Depends(JWTBearer())],
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
