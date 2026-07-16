# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Shared real-crypto helpers for federation strict-enrollment tests.

Strict enrollment (Phase 12 out-of-band trust) requires a REAL Ed25519
identity keypair, a REAL X.509 cert (so it can be fingerprinted), and a
valid enrollment proof binding the two.  The old fixtures used dummy strings
(``tls_cert_pem="c"``) which no longer pass the strict gate, so these helpers
mint the genuine artefacts once, in one place.

Certs are Ed25519-signed (fast keygen, no key-size knob) — the fingerprint is
over the DER regardless of algorithm, so this is fine for tests even though
production federation certs are RSA.
"""

from __future__ import annotations

import base64
import datetime
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes  # noqa: F401  (kept for parity)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID

from backend.services import federation_identity_service as identity_svc


def make_identity_keypair() -> Tuple[Ed25519PrivateKey, str]:
    """Return ``(private_key, public_pem_str)`` for a federation identity."""
    priv = Ed25519PrivateKey.generate()
    pub_pem = (
        priv.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return priv, pub_pem


def make_self_signed_cert(common_name: str = "test-peer") -> str:
    """Mint a throwaway Ed25519-signed self-signed X.509 cert (PEM str)."""
    key = Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .sign(key, None)  # Ed25519 → algorithm must be None
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def sign_enrollment_proof(
    identity_private_key: Ed25519PrivateKey, *, role: str, tls_cert_pem: str
) -> str:
    """Sign the canonical enrollment proof for ``tls_cert_pem`` with a given
    identity private key (the peer's, not necessarily this server's on-disk
    key) — exactly what the engine's signing side produces."""
    message = identity_svc.enrollment_proof_message(
        role=role, tls_cert_pem=tls_cert_pem
    )
    return base64.b64encode(identity_private_key.sign(message)).decode("ascii")


def enroll_site(session, *, name: str, url: str, **create_kwargs):
    """Full strict coordinator-side enrollment with generated identity + cert.

    Returns ``(site, sync_bearer, coord_outbound)`` — the tuple
    ``complete_enrollment`` returns — so callers needing the bearers can use
    them.  See :func:`quick_enroll` when you only need the enrolled site."""
    from backend.services import federation_site_service as ssvc  # noqa: PLC0415

    site_priv, site_pub_pem = make_identity_keypair()
    site_cert = make_self_signed_cert(common_name=name)
    _site, token = ssvc.create_site(
        session,
        name=name,
        url=url,
        site_identity_public_key_pem=site_pub_pem,
        **create_kwargs,
    )
    proof = sign_enrollment_proof(site_priv, role="site", tls_cert_pem=site_cert)
    return ssvc.complete_enrollment(
        session,
        plaintext_token=token,
        tls_cert_pem=site_cert,
        identity_proof_b64=proof,
    )


def quick_enroll(session, *, name: str, url: str, **create_kwargs):
    """Strict-enroll a site and return just the ``FederationSite`` row."""
    site, _sync_bearer, _coord_outbound = enroll_site(
        session, name=name, url=url, **create_kwargs
    )
    return site
