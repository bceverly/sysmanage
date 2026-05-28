"""Air-gap manifest signing-key management (collector side) + key access.

Zero-touch keypair lifecycle for the collector's ed25519 manifest
signing key:

  * ``ensure_collector_keypair()`` generates the private+public PEM pair
    at the configured canonical path the first time it's called with no
    existing private key (triggered when the operator sets the server
    role to ``collector``).  It NEVER overwrites an existing private
    key — rotation is a deliberate operator action, not a side effect.
  * ``get_collector_private_key_pem()`` / ``get_collector_public_key_pem()``
    read them back for the sign step / bundle-embed step.

The actual ed25519 sign happens in the Pro+ collector engine's
``sign_manifest(manifest_dict, private_key_pem)``; this service only
manages where the key lives and hands the PEM to the engine.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.config import config as config_module

logger = logging.getLogger(__name__)


def _public_key_path(private_key_path: str) -> str:
    """Sibling ``.pub`` path next to the private key."""
    base, _ = os.path.splitext(private_key_path)
    return base + ".pub"


def ensure_collector_keypair() -> Tuple[str, str]:
    """Generate the collector ed25519 keypair if the private key is absent.

    Returns ``(private_path, public_path)``.  Idempotent: if the private
    key already exists it's left untouched (so this is safe to call on
    every role-set / startup) and the public key is re-derived from it
    if the ``.pub`` is missing.  Writes 0600 private / 0644 public.

    Raises on a genuine IO/permission failure so the caller (the role
    PUT handler) can surface it rather than silently leaving the
    collector unable to sign.
    """
    private_path = config_module.get_airgap_signing_key_file()
    public_path = _public_key_path(private_path)
    os.makedirs(os.path.dirname(private_path), exist_ok=True)

    if os.path.isfile(private_path):
        # Private key already present — never overwrite.  Just make sure
        # the public sibling exists (re-derive if someone deleted it).
        if not os.path.isfile(public_path):
            _write_public_from_private(private_path, public_path)
        return private_path, public_path

    logger.info("Generating collector ed25519 signing keypair at %s", private_path)
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
    # Write private with a tight umask-independent 0600 via opener.
    _atomic_write(private_path, private_pem, 0o600)
    _atomic_write(public_path, public_pem, 0o644)
    return private_path, public_path


def _write_public_from_private(private_path: str, public_path: str) -> None:
    with open(private_path, "rb") as fh:
        private_key = serialization.load_pem_private_key(fh.read(), password=None)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _atomic_write(public_path, public_pem, 0o644)


def _atomic_write(path: str, data: bytes, mode: int) -> None:
    """Write ``data`` to ``path`` with explicit ``mode``, no race window
    where the file exists world-readable before chmod."""
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


def get_collector_private_key_pem() -> Optional[str]:
    """Return the collector's private signing PEM, or None if not present."""
    path = config_module.get_airgap_signing_key_file()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def get_collector_public_key_pem() -> Optional[str]:
    """Return the collector's public PEM (for embedding into bundles)."""
    path = _public_key_path(config_module.get_airgap_signing_key_file())
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        # Re-derive from the private key if the .pub went missing.
        try:
            ensure_collector_keypair()
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except Exception:  # pylint: disable=broad-exception-caught
            return None
