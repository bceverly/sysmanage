# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy's certificate, from the SysManage CA (ROADMAP 25.5).

Decided (Bryan, 2026-11-10): the proxy's TLS certificate is issued by the
SysManage CA, so hosts trust it through that CA -- sent as the target's CA --
with nothing copied or pinned by hand, and the server renews it.

* **The key never leaves the storage host.**  Each storage configure carries
  ``cert``: the name hosts reach the proxy at, the certificate the server has
  for it (or none), and whether a new one is wanted.  When one is, the storage
  host's agent makes a key, keeps it, and answers with a certificate request
  (``proxy_csr``); the server signs it for the target's name -- the request
  gives only its public key -- keeps the certificate on the target and sends
  it with the next configure, when the agent installs both and restarts the
  proxy.
* **Renewed before it lapses**: a certificate that names another address (the
  target's was changed), is not the SysManage CA's, or ends within
  ``RENEW_DAYS`` is wanted again.
* **An operator's own CA wins.**  A site CA set on the target is what hosts
  trust; the server then sends no certificate of its own.
"""

import ipaddress
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from sqlalchemy.orm import Session

from backend.persistence import models

logger = logging.getLogger(__name__)

RENEW_DAYS = 30
MAX_CSR_BYTES = 16 * 1024


def _manager():
    # pylint: disable=import-outside-toplevel
    from backend.security.certificate_manager import certificate_manager

    return certificate_manager


def _ca_pem() -> str:
    return _manager().get_ca_certificate().decode("ascii")


def managed(target: Optional[models.BackupTarget]) -> bool:
    """The server issues this proxy's certificate: the target is on the
    proxy and the operator has set no site CA of their own."""
    # pylint: disable=import-outside-toplevel
    from backend.services import backup_proxy  # noqa: PLC0415

    return backup_proxy.uses_proxy(target) and not target.proxy_ca_pem


def _names(cert: x509.Certificate) -> set:
    try:
        alt = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return set()
    found = {str(name).lower() for name in alt.value.get_values_for_type(x509.DNSName)}
    found |= {str(ip) for ip in alt.value.get_values_for_type(x509.IPAddress)}
    return found


def _normal(name: str) -> str:
    try:
        return str(ipaddress.ip_address(name.strip("[]")))
    except ValueError:
        return name.lower()


def _current(target: models.BackupTarget, now: Optional[datetime] = None) -> bool:
    """The certificate the server holds still serves: it names the target's
    proxy address, the SysManage CA signed it, and it is not near its end."""
    if not target.proxy_cert_pem:
        return False
    try:
        cert = x509.load_pem_x509_certificate(target.proxy_cert_pem.encode("ascii"))
        ca = x509.load_pem_x509_certificate(_ca_pem().encode("ascii"))
        cert.verify_directly_issued_by(ca)
    except (ValueError, TypeError, InvalidSignature, UnicodeEncodeError):
        return False
    now = now or datetime.now(timezone.utc)
    if cert.not_valid_after_utc - timedelta(days=RENEW_DAYS) <= now:
        return False
    return _normal(target.proxy_host or "") in _names(cert)


def storage_block(target: models.BackupTarget) -> Optional[Dict[str, Any]]:
    """``cert`` for the storage side's ``proxy``, or None when the server
    issues no certificate for this target (NFS, or the operator's own CA)."""
    if not managed(target):
        return None
    current = _current(target)
    return {
        "name": _normal(target.proxy_host),
        "pem": target.proxy_cert_pem if current else None,
        "renew": not current,
    }


def host_ca(target: models.BackupTarget) -> Optional[str]:
    """What hosts trust the proxy through when the server issued its
    certificate: the SysManage CA."""
    return _ca_pem() if managed(target) and target.proxy_cert_pem else None


class CsrRefused(ValueError):
    """A proxy certificate request that cannot be signed; the message says why."""


def _public_key(csr_pem: Any):
    if not isinstance(csr_pem, str) or len(csr_pem) > MAX_CSR_BYTES:
        raise CsrRefused("The proxy certificate request is not a PEM request")
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise CsrRefused("The proxy certificate request could not be read") from error
    if not csr.is_signature_valid:
        raise CsrRefused("The proxy certificate request's signature is not valid")
    key = csr.public_key()
    if isinstance(key, ec.EllipticCurvePublicKey):
        if key.curve.name not in ("secp256r1", "secp384r1"):
            raise CsrRefused("The proxy key's curve is not supported")
    elif isinstance(key, rsa.RSAPublicKey):
        if key.key_size < 2048:
            raise CsrRefused("The proxy's RSA key must be at least 2048 bits")
    else:
        raise CsrRefused("The proxy's key type is not supported")
    return key


def _same_key(cert_pem: str, key) -> bool:
    spki = serialization.PublicFormat.SubjectPublicKeyInfo
    der = serialization.Encoding.DER
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("ascii"))
    except ValueError:
        return False
    return cert.public_key().public_bytes(der, spki) == key.public_bytes(der, spki)


def store_csr(db: Session, policy: Optional[models.BackupPolicy], reply: Any) -> bool:
    """Sign the storage host's request when the target wants a certificate;
    True when one was issued (every policy on the target is then re-sent, so
    the storage host gets it with its next configure)."""
    csr = reply.get("proxy_csr") if isinstance(reply, dict) else None
    if policy is None or not csr:
        return False
    target = (
        db.query(models.BackupTarget)
        .filter(models.BackupTarget.id == policy.target_id)
        .first()
    )
    if target is None or not managed(target):
        return False  # not ours to issue
    try:
        key = _public_key(csr)
    except CsrRefused as refused:
        logger.warning("Proxy certificate request for target %s refused: %s",
                       target.id, refused)  # fmt: skip
        return False
    if _current(target) and _same_key(target.proxy_cert_pem, key):
        # Issued already, from an earlier reply with this key (a storage host
        # with several policies asks in each).  A request with ANOTHER key
        # means the storage host no longer has the one the certificate is
        # for, so it is issued again.
        return False
    cert = _manager().issue_proxy_certificate(key, _normal(target.proxy_host))
    target.proxy_cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    for other in (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    ):
        other.config_version += 1
    logger.info("Issued restate-proxy certificate for %s (target %s), until %s",
                target.proxy_host, target.id, cert.not_valid_after_utc)  # fmt: skip
    return True


def view(target: models.BackupTarget) -> Optional[Dict[str, Any]]:
    """The certificate, for the Backups page: issued, and until when."""
    if not managed(target) or not target.proxy_cert_pem:
        return None
    try:
        cert = x509.load_pem_x509_certificate(target.proxy_cert_pem.encode("ascii"))
    except ValueError:
        return None
    return {
        "expires": cert.not_valid_after_utc.isoformat(),
        "current": _current(target),
    }
