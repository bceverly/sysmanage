# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

# Trusted-collector key filenames: keep them tame so they map 1:1 to a
# filesystem path with no traversal.  Operator-supplied "name" is
# slugified to this charset before becoming ``<name>.pub``.
_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


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


# ---------------------------------------------------------------------------
# Fingerprints + trusted-collector keyring (repository side)
# ---------------------------------------------------------------------------
def _canonical_public_pem(pem: str | bytes) -> bytes:
    """Load an Ed25519 public PEM and re-serialise it to the canonical
    SubjectPublicKeyInfo PEM bytes.  Raises ``ValueError`` if the input
    isn't a valid Ed25519 public key.  Re-serialising means an operator
    can paste a key with odd whitespace and still get the same
    fingerprint the collector computed.
    """
    raw = pem.encode("utf-8") if isinstance(pem, str) else pem
    pub = serialization.load_pem_public_key(raw)
    if not isinstance(pub, Ed25519PublicKey):
        raise ValueError("not an Ed25519 public key")
    return pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def fingerprint_of_public_pem(pem: str | bytes) -> str:
    """SHA-256 hex of the canonical public PEM — identical to the
    ``signer_fingerprint`` the collector engine stamps into a manifest
    (``sha256(public_bytes(PEM, SubjectPublicKeyInfo))``).
    """
    return hashlib.sha256(_canonical_public_pem(pem)).hexdigest()


def get_collector_public_key_fingerprint() -> Optional[str]:
    """Fingerprint of THIS server's collector public key, or None."""
    pem = get_collector_public_key_pem()
    if not pem:
        return None
    try:
        return fingerprint_of_public_pem(pem)
    except ValueError:
        return None


def _safe_key_name(name: str) -> str:
    slug = _NAME_RE.sub("-", (name or "").strip()).strip("-._")
    return slug or "collector"


def _keyring_key_path(keyring_dir: str, name: str) -> str:
    """Resolve ``<keyring_dir>/<slug>.pub`` and HARD-VERIFY it stays inside the
    keyring directory.

    ``_safe_key_name`` already strips path separators, but this adds an explicit
    realpath-containment check on top — defence in depth against path traversal
    from the caller-supplied ``name``.  Raises ``ValueError`` if the resolved
    path's parent isn't the keyring dir.
    """
    slug = _safe_key_name(name)
    base = os.path.realpath(keyring_dir)
    resolved = os.path.realpath(os.path.join(base, slug + ".pub"))
    if not resolved.startswith(base + os.sep):
        raise ValueError("resolved keyring path escapes the keyring directory")
    return resolved


def list_trusted_collectors() -> List[dict]:
    """List the repository's trusted-collector keys.

    Returns ``[{"name", "fingerprint"}]`` — ``name`` is the filename
    stem, ``fingerprint`` the sha256 of the canonical PEM (or None if
    the file isn't a parseable Ed25519 key).  Missing dir → empty list.
    """
    keyring_dir = config_module.get_airgap_collector_public_key_dir()
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


def import_trusted_collector(name: str, public_key_pem: str) -> dict:
    """Add a collector public key to the repository's trusted keyring.

    Validates it's an Ed25519 public PEM, writes the canonical form to
    ``<keyring_dir>/<slug>.pub`` (0644), and returns
    ``{"name", "fingerprint"}``.  Raises ``ValueError`` on a bad key.
    """
    canonical = _canonical_public_pem(public_key_pem)  # raises on bad key
    fingerprint = hashlib.sha256(canonical).hexdigest()
    keyring_dir = config_module.get_airgap_collector_public_key_dir()
    os.makedirs(keyring_dir, exist_ok=True)
    path = _keyring_key_path(keyring_dir, name)  # contained + traversal-safe
    # Slug from the validated, contained filename — provably free of path
    # separators / control characters, so it's safe to log + return.
    slug = os.path.splitext(os.path.basename(path))[0]
    _atomic_write(path, canonical, 0o644)
    logger.info(
        "Imported trusted collector key '%s' (fingerprint %s)",
        sanitize_log(slug),
        fingerprint,
    )
    return {"name": slug, "fingerprint": fingerprint}


def remove_trusted_collector(name: str) -> bool:
    """Delete a trusted-collector key by name (filename stem).  Returns
    True if a file was removed.  Path-traversal-safe via slugify."""
    keyring_dir = config_module.get_airgap_collector_public_key_dir()
    try:
        path = _keyring_key_path(keyring_dir, name)  # contained + traversal-safe
    except ValueError:
        return False
    slug = os.path.splitext(os.path.basename(path))[0]
    try:
        os.unlink(path)
        logger.info("Removed trusted collector key '%s'", sanitize_log(slug))
        return True
    except OSError:
        return False
