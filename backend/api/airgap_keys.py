"""Air-gap signing-key endpoints (Settings → Server Role helpers).

Two small operator surfaces that close the air-gap trust loop:

  * **Collector side** — expose THIS server's collector *public* key +
    fingerprint so the operator can copy it and hand it to a repository.
    The private signing key never leaves the box.
  * **Repository side** — import / list / remove trusted collector
    public keys (the keyring the ingest path verifies signed media
    against).

All routes require a logged-in user.  They're role-agnostic at the HTTP
layer (the UI only shows the collector card for role=collector and the
import card for role=repository), but a collector with no key yet just
gets a 404 on the collector-key GET.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.services import airgap_signing_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/airgap",
    tags=["airgap-keys"],
    dependencies=[Depends(JWTBearer())],
)


class CollectorKeyResponse(BaseModel):
    public_key_pem: str
    fingerprint: str


class TrustedCollector(BaseModel):
    name: str
    fingerprint: str | None = None


class TrustedCollectorList(BaseModel):
    trusted: list[TrustedCollector]


class ImportTrustedCollector(BaseModel):
    name: str
    public_key_pem: str


@router.get("/collector-key", response_model=CollectorKeyResponse)
def get_collector_key():
    """Return this server's collector public key + fingerprint.

    404 when no collector keypair exists yet (i.e. the role was never
    set to ``collector``, which is the trigger that mints the key).
    """
    pem = airgap_signing_service.get_collector_public_key_pem()
    fingerprint = airgap_signing_service.get_collector_public_key_fingerprint()
    if not pem or not fingerprint:
        raise HTTPException(
            status_code=404,
            detail=_(
                "No collector signing key found. Set this server's role to "
                "'Air-Gap Collector' to generate one."
            ),
        )
    return CollectorKeyResponse(public_key_pem=pem, fingerprint=fingerprint)


@router.get("/trusted-collectors", response_model=TrustedCollectorList)
def list_trusted_collectors():
    """List the repository's trusted-collector keys."""
    rows = airgap_signing_service.list_trusted_collectors()
    return TrustedCollectorList(trusted=[TrustedCollector(**row) for row in rows])


@router.post("/trusted-collectors", response_model=TrustedCollector)
def import_trusted_collector(payload: ImportTrustedCollector):
    """Import a collector public key into the trusted keyring."""
    try:
        result = airgap_signing_service.import_trusted_collector(
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
    return TrustedCollector(**result)


@router.delete("/trusted-collectors/{name}", status_code=204)
def remove_trusted_collector(name: str):
    """Remove a trusted-collector key by name."""
    if not airgap_signing_service.remove_trusted_collector(name):
        raise HTTPException(status_code=404, detail=_("Trusted key not found"))
