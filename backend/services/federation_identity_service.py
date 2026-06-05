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

import hashlib
import logging
import os
import re
from typing import List, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from backend.config import config as config_module

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
    slug = _safe_key_name(name)
    path = os.path.join(keyring_dir, slug + ".pub")
    _atomic_write(path, canonical, 0o644)
    logger.info("Imported federation peer key '%s' (fingerprint %s)", slug, fingerprint)
    return {"name": slug, "fingerprint": fingerprint}


def remove_federation_peer(name: str) -> bool:
    """Delete a trusted peer key by name (filename stem).  Path-safe."""
    keyring_dir = config_module.get_federation_peer_public_key_dir()
    slug = _safe_key_name(name)
    path = os.path.join(keyring_dir, slug + ".pub")
    try:
        os.unlink(path)
        logger.info("Removed federation peer key '%s'", slug)
        return True
    except OSError:
        return False
