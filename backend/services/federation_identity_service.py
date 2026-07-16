# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Federation identity-key management (Phase 12 — Server Role UI).

Zero-touch ed25519 identity keypair for THIS server's federation trust
anchor — the public key an operator hands to the peer (coordinator ⇄ site)
so each side can pin the other's identity, mirroring the air-gap
collector/repository key exchange.

  * ``ensure_federation_identity_keypair()`` generates the private+public
    PEM pair at the configured path the first time it's needed (server
    startup / when a federation role is chosen).  NEVER overwrites an
    existing private key — rotation is a deliberate operator action.
  * ``get_federation_identity_public_key_pem()`` / ``..._fingerprint()``
    read the key + its fingerprint for the operator to copy.
  * ``import_federation_peer`` / ``list`` / ``remove`` manage the trusted
    peer keyring (the keys pasted in from the other box).

The key material is exactly what the air-gap signing service uses; this is
a deliberate copy so the two role exchanges feel identical to the operator.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import logging
import os
import re
import socket
from typing import List, Optional, Tuple

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.x509.oid import NameOID

from backend.config import config as config_module
from backend.utils.verbosity_logger import sanitize_log

# Federation TLS cert validity.  Long-lived (10y) — it's a pinned, self-
# signed identity cert, not a CA-chained web cert, so rotation is a
# deliberate operator action rather than a calendar event.
_TLS_CERT_DAYS = 3650
_TLS_BACKDATE_SECONDS = 300  # tolerate small clock skew between peers

logger = logging.getLogger(__name__)

# Peer-key filenames slugified to this charset → no path traversal.
_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _public_key_path(private_key_path: str) -> str:
    base, _ = os.path.splitext(private_key_path)
    return base + ".pub"


def _atomic_write(path: str, data: bytes, mode: int) -> None:
    """Write with explicit mode, no world-readable race window before chmod."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        os.chmod(path, mode)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _write_public_from_private(private_path: str, public_path: str) -> None:
    with open(private_path, "rb") as fh:
        private_key = serialization.load_pem_private_key(fh.read(), password=None)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _atomic_write(public_path, public_pem, 0o644)


def ensure_federation_identity_keypair() -> Tuple[str, str]:
    """Generate the federation identity ed25519 keypair if absent.

    Returns ``(private_path, public_path)``.  Idempotent: an existing
    private key is left untouched (safe to call on every startup), and the
    public sibling is re-derived if it went missing.  0600 private / 0644
    public.  Raises on a genuine IO/permission failure.
    """
    private_path = config_module.get_federation_identity_key_file()
    public_path = _public_key_path(private_path)
    os.makedirs(os.path.dirname(private_path), exist_ok=True)

    if os.path.isfile(private_path):
        if not os.path.isfile(public_path):
            _write_public_from_private(private_path, public_path)
        return private_path, public_path

    logger.info("Generating federation identity ed25519 keypair at %s", private_path)
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _atomic_write(private_path, private_pem, 0o600)
    _atomic_write(public_path, public_pem, 0o644)
    return private_path, public_path


def get_federation_identity_public_key_pem() -> Optional[str]:
    """This server's federation identity public PEM (auto-creates if absent)."""
    path = _public_key_path(config_module.get_federation_identity_key_file())
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        try:
            ensure_federation_identity_keypair()
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except Exception:  # pylint: disable=broad-exception-caught
            return None


# ---------------------------------------------------------------------------
# Federation TLS certificate (mutual-TLS pinning material)
# ---------------------------------------------------------------------------
#
# The enrollment handshake exchanges X.509 certs so each side can pin the
# other for mutual TLS.  We auto-mint a self-signed cert so the operator
# never has to generate or paste one — enrollment is just URL + token.


def _tls_key_path(cert_path: str) -> str:
    base, _ = os.path.splitext(cert_path)
    return base + "-key.pem"


def ensure_federation_tls_cert() -> Tuple[str, str]:
    """Generate this server's self-signed federation TLS cert if absent.

    Returns ``(cert_path, key_path)``.  Idempotent and NEVER overwrites — the
    cert is pinned by the peer at enrollment time, so regenerating it would
    silently break an existing federation relationship.  0644 cert / 0600 key.
    """
    cert_path = config_module.get_federation_tls_cert_file()
    key_path = _tls_key_path(cert_path)
    os.makedirs(os.path.dirname(cert_path), exist_ok=True)

    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        return cert_path, key_path

    logger.info("Generating federation TLS certificate at %s", cert_path)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    # X.509 CommonName is capped at 64 chars; CI/cloud hostnames and long FQDNs
    # can exceed that (and would raise ValueError).  The cert is pinned by
    # fingerprint at enrollment, not by CN, so truncating is purely cosmetic.
    common_name = (socket.gethostname() or "sysmanage-federation")[:64]
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(seconds=_TLS_BACKDATE_SECONDS))
        .not_valid_after(now + datetime.timedelta(days=_TLS_CERT_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    _atomic_write(key_path, key_pem, 0o600)
    _atomic_write(cert_path, cert_pem, 0o644)
    return cert_path, key_path


def get_federation_tls_cert_pem() -> Optional[str]:
    """This server's federation TLS cert PEM (auto-creates if absent)."""
    cert_path = config_module.get_federation_tls_cert_file()
    try:
        with open(cert_path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        try:
            ensure_federation_tls_cert()
            with open(cert_path, "r", encoding="utf-8") as fh:
                return fh.read()
        except Exception:  # pylint: disable=broad-exception-caught
            return None


# ---------------------------------------------------------------------------
# Wire-request signing (proof the sender holds the pinned cert's private key)
# ---------------------------------------------------------------------------
#
# Each federation wire request is signed with the sender's federation TLS
# private key (RSA / PKCS1v15-SHA256 over the exact request bytes); the
# receiver verifies against the cert it pinned for that peer at enrollment.
# This is what turns the pinned certs from "stored" into "enforced" — a
# leaked bearer alone can't impersonate a peer without its private key.  The
# receiver only *enforces* under HTTPS (see ``config.federation_enforce_cert_pinning``);
# on plain-HTTP dev deployments the signature is attached but ignored.


def sign_federation_request(body: bytes) -> Optional[str]:
    """Sign request bytes with this server's federation TLS private key.

    Returns a base64 signature, or ``None`` on any failure so the caller can
    fail open (send unsigned) rather than stall the federation on a keygen
    hiccup — the receiver decides whether to require it.
    """
    try:
        ensure_federation_tls_cert()
        key_path = _tls_key_path(config_module.get_federation_tls_cert_file())
        with open(key_path, "rb") as fh:
            private_key = serialization.load_pem_private_key(fh.read(), password=None)
        # RSA PKCS#1 v1.5 *signatures* (unlike v1.5 encryption) are not broken;
        # the peer verifies against the cert it pinned at enrollment, and moving
        # to PSS would break every already-established federation relationship.
        # nosemgrep: python.cryptography.cryptography-rsa-pkcs1-signature.cryptography-rsa-pkcs1-signature
        signature = private_key.sign(body, padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode("ascii")
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Could not sign federation request", exc_info=True)
        return None


def verify_federation_request(
    body: bytes, signature_b64: str, peer_cert_pem: str | bytes
) -> bool:
    """Verify a base64 signature over ``body`` against a peer's pinned cert.

    Returns ``False`` (never raises) on a bad signature, malformed cert, or
    any decode error — the caller turns that into a 401.
    """
    if not signature_b64 or not peer_cert_pem:
        return False
    try:
        raw_cert = (
            peer_cert_pem.encode("utf-8")
            if isinstance(peer_cert_pem, str)
            else peer_cert_pem
        )
        cert = x509.load_pem_x509_certificate(raw_cert)
        # Verifies the PKCS#1 v1.5 signature made by ``sign_federation_request``
        # against the pinned peer cert — see that function re: PKCS1v15 vs PSS.
        # nosemgrep: python.cryptography.cryptography-rsa-pkcs1-signature.cryptography-rsa-pkcs1-signature
        cert.public_key().verify(
            base64.b64decode(signature_b64),
            body,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
    except Exception:  # pylint: disable=broad-exception-caught
        return False


# ---------------------------------------------------------------------------
# Fingerprints + trusted-peer keyring
# ---------------------------------------------------------------------------


def _canonical_public_pem(pem: str | bytes) -> bytes:
    """Re-serialise an Ed25519 public PEM to canonical bytes (so pasted
    whitespace doesn't change the fingerprint).  Raises ``ValueError`` if
    it isn't a valid Ed25519 public key."""
    raw = pem.encode("utf-8") if isinstance(pem, str) else pem
    pub = serialization.load_pem_public_key(raw)
    if not isinstance(pub, Ed25519PublicKey):
        raise ValueError("not an Ed25519 public key")
    return pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def fingerprint_of_public_pem(pem: str | bytes) -> str:
    """SHA-256 hex of the canonical public PEM."""
    return hashlib.sha256(_canonical_public_pem(pem)).hexdigest()


def get_federation_identity_public_key_fingerprint() -> Optional[str]:
    """Fingerprint of THIS server's federation identity public key, or None."""
    pem = get_federation_identity_public_key_pem()
    if not pem:
        return None
    try:
        return fingerprint_of_public_pem(pem)
    except ValueError:
        return None


def _safe_key_name(name: str) -> str:
    slug = _NAME_RE.sub("-", (name or "").strip()).strip("-._")
    return slug or "peer"


def _keyring_key_path(keyring_dir: str, name: str) -> str:
    """Resolve ``<keyring_dir>/<slug>.pub`` and HARD-VERIFY it stays inside the
    keyring directory.

    ``_safe_key_name`` already strips path separators, but this adds an explicit
    realpath-containment check on top — defence in depth, and an unambiguous
    guard against path traversal from the caller-supplied ``name``.  Raises
    ``ValueError`` if the resolved path's parent isn't the keyring dir.
    """
    slug = _safe_key_name(name)
    base = os.path.realpath(keyring_dir)
    resolved = os.path.realpath(os.path.join(base, slug + ".pub"))
    if not resolved.startswith(base + os.sep):
        raise ValueError("resolved keyring path escapes the keyring directory")
    return resolved


def list_federation_peers() -> List[dict]:
    """List the trusted federation peer keys as ``[{"name", "fingerprint"}]``."""
    keyring_dir = config_module.get_federation_peer_public_key_dir()
    out: List[dict] = []
    try:
        names = sorted(os.listdir(keyring_dir))
    except OSError:
        return out
    for fname in names:
        path = os.path.join(keyring_dir, fname)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                pem = fh.read()
            fp = fingerprint_of_public_pem(pem)
        except (OSError, ValueError):
            fp = None
        stem, _ext = os.path.splitext(fname)
        out.append({"name": stem, "fingerprint": fp})
    return out


def import_federation_peer(name: str, public_key_pem: str) -> dict:
    """Add a peer's federation public key to the trusted keyring.

    Validates it's an Ed25519 public PEM, writes the canonical form to
    ``<keyring_dir>/<slug>.pub`` (0644), returns ``{"name", "fingerprint"}``.
    Raises ``ValueError`` on a bad key.
    """
    canonical = _canonical_public_pem(public_key_pem)  # raises on bad key
    fingerprint = hashlib.sha256(canonical).hexdigest()
    keyring_dir = config_module.get_federation_peer_public_key_dir()
    os.makedirs(keyring_dir, exist_ok=True)
    path = _keyring_key_path(keyring_dir, name)  # contained + traversal-safe
    # Slug is taken from the validated, contained filename — provably free of
    # path separators / control characters, so it's safe to log + return.
    slug = os.path.splitext(os.path.basename(path))[0]
    _atomic_write(path, canonical, 0o644)
    logger.info(
        "Imported federation peer key '%s' (fingerprint %s)",
        sanitize_log(slug),
        fingerprint,
    )
    return {"name": slug, "fingerprint": fingerprint}


def remove_federation_peer(name: str) -> bool:
    """Delete a trusted peer key by name (filename stem).  Path-safe."""
    keyring_dir = config_module.get_federation_peer_public_key_dir()
    try:
        path = _keyring_key_path(keyring_dir, name)  # contained + traversal-safe
    except ValueError:
        return False
    slug = os.path.splitext(os.path.basename(path))[0]
    try:
        os.unlink(path)
        logger.info("Removed federation peer key '%s'", sanitize_log(slug))
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Ed25519 identity signing + enrollment proof (Phase 12 — strict out-of-band
# trust).
#
# The pinned TLS cert closes the channel AFTER enrollment, but the cert itself
# is fetched over the (possibly hostile) network DURING enrollment — classic
# trust-on-first-use.  The enrollment token can't fix that: it's a bearer
# secret that transits the same channel, so an active MITM relays it and pins
# itself on both sides.
#
# The ed25519 identity key is the fix BECAUSE its private half never transits
# the wire.  The operator exchanges the *public* identity key OUT OF BAND
# (it's public — phone, wiki, config-mgmt — secrecy doesn't matter), the peer
# signs the exact cert it's offering, and the receiver verifies that signature
# against the pre-loaded public key before pinning.  A swapped cert fails; a
# MITM without the private key can't forge the proof.  Bonus: because the proof
# is over the cert *fingerprint*, rotating the TLS cert is just a re-sign by the
# same identity — no re-exchange.
# ---------------------------------------------------------------------------

ENROLLMENT_PROOF_CONTEXT = "sysmanage-federation-enroll-v1"


def _load_identity_private_key() -> Ed25519PrivateKey:
    """Load (auto-creating if absent) this server's Ed25519 identity private key."""
    ensure_federation_identity_keypair()
    private_path = config_module.get_federation_identity_key_file()
    with open(private_path, "rb") as fh:
        key = serialization.load_pem_private_key(fh.read(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("federation identity key is not an Ed25519 private key")
    return key


def tls_cert_fingerprint(cert_pem: str | bytes) -> str:
    """SHA-256 hex of a PEM X.509 cert's DER bytes — the standard cert
    fingerprint operators compare.  Raises ``ValueError`` on a non-cert."""
    raw = cert_pem.encode("utf-8") if isinstance(cert_pem, str) else cert_pem
    cert = x509.load_pem_x509_certificate(raw)
    return hashlib.sha256(
        cert.public_bytes(encoding=serialization.Encoding.DER)
    ).hexdigest()


def sign_with_identity_key(message: bytes) -> Optional[str]:
    """Ed25519-sign ``message`` with this server's identity private key.

    Returns base64, or ``None`` on any failure so a keygen/IO hiccup can't
    wedge the caller — the *receiver* decides whether a missing proof is fatal
    (in strict mode it is)."""
    try:
        key = _load_identity_private_key()
        return base64.b64encode(key.sign(message)).decode("ascii")
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Could not sign with federation identity key", exc_info=True)
        return None


def verify_with_peer_identity_key(
    message: bytes, signature_b64: str, peer_public_pem: str | bytes
) -> bool:
    """Verify an Ed25519 ``signature_b64`` over ``message`` against a peer's
    out-of-band-exchanged identity public key.

    Returns ``False`` (never raises) on a bad signature, non-Ed25519 key,
    malformed PEM, or decode error — the caller turns that into a 401/400."""
    if not signature_b64 or not peer_public_pem:
        return False
    try:
        raw = (
            peer_public_pem.encode("utf-8")
            if isinstance(peer_public_pem, str)
            else peer_public_pem
        )
        pub = serialization.load_pem_public_key(raw)
        if not isinstance(pub, Ed25519PublicKey):
            return False
        pub.verify(base64.b64decode(signature_b64), message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def enrollment_proof_message(*, role: str, tls_cert_pem: str | bytes) -> bytes:
    """Canonical bytes a party signs to prove its out-of-band identity vouches
    for the exact TLS cert it is presenting.

    Bound to: a fixed context string (no cross-protocol signature reuse), the
    signer's ``role`` ("coordinator" | "site", so a coordinator proof can't be
    replayed as a site proof), and the SHA-256 fingerprint of the cert being
    pinned.  Raises ``ValueError`` on a bad role or non-cert PEM."""
    role_norm = (role or "").strip().lower()
    if role_norm not in ("coordinator", "site"):
        raise ValueError("role must be 'coordinator' or 'site'")
    fingerprint = tls_cert_fingerprint(tls_cert_pem)
    return f"{ENROLLMENT_PROOF_CONTEXT}|{role_norm}|{fingerprint}".encode("utf-8")


def build_enrollment_proof(*, role: str, tls_cert_pem: str | bytes) -> Optional[str]:
    """Sign the enrollment proof for our OWN TLS cert (the one the peer pins).

    Returns base64 signature, or ``None`` if signing fails or the cert is
    unparseable."""
    try:
        message = enrollment_proof_message(role=role, tls_cert_pem=tls_cert_pem)
    except ValueError:
        return None
    return sign_with_identity_key(message)


def verify_enrollment_proof(
    *,
    role: str,
    tls_cert_pem: str | bytes,
    signature_b64: str,
    peer_identity_public_pem: str | bytes,
) -> bool:
    """Strictly verify a peer's enrollment proof.

    Confirms the pre-loaded (out-of-band) ``peer_identity_public_pem`` signed
    EXACTLY ``tls_cert_pem`` for the given ``role``.  Any missing input, a bad
    cert, or a signature mismatch → ``False``.  This is the gate that turns
    TOFU into authenticated pinning."""
    if not (tls_cert_pem and signature_b64 and peer_identity_public_pem):
        return False
    try:
        message = enrollment_proof_message(role=role, tls_cert_pem=tls_cert_pem)
    except ValueError:
        return False
    return verify_with_peer_identity_key(
        message, signature_b64, peer_identity_public_pem
    )
