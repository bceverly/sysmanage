"""
Symmetric encryption for MFA-at-rest secrets.

TOTP shared secrets are stored encrypted in the database so a leaked
DB dump alone can't be replayed against the authenticator app.  We use
Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from the server's
configured MFA encryption key — separate from the JWT signing key so
key rotation can happen independently.

Key resolution order:
1. ``security.mfa_encryption_key`` in ``/etc/sysmanage.yaml`` (preferred —
   operators can rotate this key separately from JWT signing).
2. Fallback: derive from ``security.jwt_secret`` via HKDF-SHA256.  This
   makes the feature work out of the box without forcing operators to
   regenerate config, but the key rotates only when JWT_SECRET does.
"""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from backend.config import config

_HKDF_INFO = b"sysmanage-mfa-encryption-v1"
_HKDF_SALT = b"sysmanage-mfa-key-salt"


def _resolve_key() -> bytes:
    """Return the 32-byte Fernet key, deriving from JWT_SECRET if necessary."""
    cfg = config.get_config().get("security", {})
    explicit = cfg.get("mfa_encryption_key")
    if explicit:
        # Accept either a raw 32-byte URL-safe-base64 Fernet key or any
        # arbitrary string we run through HKDF to land at one.
        try:
            decoded = base64.urlsafe_b64decode(explicit.encode())
        except (ValueError, TypeError):
            decoded = b""
        if len(decoded) == 32:
            return explicit.encode()
        return base64.urlsafe_b64encode(
            HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=_HKDF_SALT,
                info=_HKDF_INFO,
            ).derive(explicit.encode())
        )
    jwt_secret = cfg.get("jwt_secret")
    if not jwt_secret:
        raise RuntimeError(
            "MFA encryption requires either security.mfa_encryption_key or "
            "security.jwt_secret to be set in /etc/sysmanage.yaml"
        )
    return base64.urlsafe_b64encode(
        HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_HKDF_SALT,
            info=_HKDF_INFO,
        ).derive(jwt_secret.encode())
    )


def _fernet() -> Fernet:
    return Fernet(_resolve_key())


def encrypt_totp_secret(plaintext: str) -> str:
    """Encrypt a TOTP secret for at-rest storage; returns ASCII ciphertext."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_totp_secret(ciphertext: str) -> str:
    """Reverse of ``encrypt_totp_secret``.  Raises ``InvalidToken`` if the
    ciphertext can't be decrypted under the current key (typically a key
    rotation that lost the old key)."""
    return _fernet().decrypt(ciphertext.encode()).decode()
