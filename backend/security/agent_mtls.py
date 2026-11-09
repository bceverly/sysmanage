# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Agent mutual TLS and server pinning (ROADMAP 25.10).

HOW A CERTIFICATE REACHES THE BACKEND
-------------------------------------
nginx asks every client for a certificate (``ssl_verify_client
optional_no_ca``), advertising only the SysManage CA so browsers never prompt,
and forwards whatever the client presented as ``X-SSL-Client-Cert``
(``$ssl_client_escaped_cert``: the URL-escaped PEM).  nginx has already proved
the client holds the certificate's private key -- the TLS handshake requires
it -- but verifies nothing else; this module checks the rest: signed by our
CA, in date, naming the host the token says it is, and carrying the host's
current serial (so a revoked or deleted host's certificate is refused at once,
with no revocation list to distribute).  nginx sets the header from its own
variable on every proxied request, so a client cannot supply one itself.

ROLLOUT, PER TENANT (``agent_mtls_mode``)
-----------------------------------------
  off       certificates are ignored.
  optional  (default) a presented certificate must be valid for this host;
            none, or an expired one, still passes on the host token.
  enforced  a valid certificate for this host is required.

SERVER PINNING
--------------
Agents pin this server's CA at enrollment.  The TLS certificate nginx serves is
usually a public one that changes every renewal, so the server publishes a
statement, signed with its CA-issued identity key, naming the TLS public keys
it serves now; an agent accepts a new TLS key only when such a statement names
exactly the key it observed.  See ``identity_document``.
"""

import base64
import hashlib
import json
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import unquote, urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from backend.i18n import _
from backend.security.certificate_manager import certificate_manager
from backend.utils.verbosity_logger import get_logger, sanitize_log

logger = get_logger("backend.security.agent_mtls")

CLIENT_CERT_HEADER = "x-ssl-client-cert"

MODE_SETTING = "agent_mtls_mode"
MODE_OFF = "off"
MODE_OPTIONAL = "optional"
MODE_ENFORCED = "enforced"
MODES = (MODE_OFF, MODE_OPTIONAL, MODE_ENFORCED)
DEFAULT_MODE = MODE_OPTIONAL

# Verdicts on what a connection presented.
NONE = "none"
VALID = "valid"
EXPIRED = "expired"
UNTRUSTED = "untrusted"  # not issued by this server's CA
WRONG_HOST = "wrong_host"
REVOKED = "revoked"  # ours, for this host, but not its current serial

# Error codes the agent understands (WebSocket error_type / REST detail.code).
CERT_REQUIRED = "host_certificate_required"
CERT_INVALID = "host_certificate_invalid"
CERT_EXPIRED = "host_certificate_expired"

# Renew 30 days before expiry; accept the replaced serial for a day.
RENEW_BEFORE = timedelta(days=30)
PREVIOUS_SERIAL_GRACE = timedelta(days=1)
STATEMENT_LIFETIME = timedelta(days=7)
# How stale "last presented" may get before a connection refreshes it: polls
# come every few seconds, and a write on each would be pure load.
PRESENTED_REFRESH = timedelta(hours=1)
_SPKI_CACHE_SECONDS = 600


@dataclass
class Decision:
    """Whether a connection may proceed, and why not when it may not."""

    allowed: bool
    verdict: str
    code: Optional[str] = None
    message: Optional[str] = None
    noted: bool = False  # the host row was changed and needs a commit


# --- the presented certificate ---------------------------------------------


def presented_certificate(header_value: Optional[str]) -> Optional[x509.Certificate]:
    """The certificate nginx forwarded, or None (absent or unparseable)."""
    if not header_value:
        return None
    try:
        return x509.load_pem_x509_certificate(unquote(header_value).encode())
    except ValueError:
        logger.warning("A client certificate was forwarded but could not be parsed")
        return None


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _host_id_of(cert: x509.Certificate) -> Optional[str]:
    values = cert.subject.get_attributes_for_oid(
        x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME
    )
    return str(values[0].value) if values else None


def _serial_accepted(host, serial: str, now: datetime) -> bool:
    if serial == (host.certificate_serial or ""):
        return True
    issued = host.certificate_issued_at
    return bool(
        host.previous_certificate_serial
        and serial == host.previous_certificate_serial
        and issued is not None
        and now - issued <= PREVIOUS_SERIAL_GRACE
    )


def verdict_for(cert: Optional[x509.Certificate], host, now=None) -> str:
    """What ``cert`` is, for ``host`` (a Host row, or None for no such host)."""
    if cert is None:
        return NONE
    try:
        cert.verify_directly_issued_by(_ca_certificate())
    except Exception:  # pylint: disable=broad-exception-caught
        return UNTRUSTED
    now = now or _naive_utc(datetime.now(timezone.utc))
    if not (
        _naive_utc(cert.not_valid_before_utc)
        <= now
        <= _naive_utc(cert.not_valid_after_utc)
    ):
        return EXPIRED
    if host is None or _host_id_of(cert) != str(host.id):
        return WRONG_HOST
    if not _serial_accepted(host, str(cert.serial_number), now):
        return REVOKED
    return VALID


def _ca_certificate() -> x509.Certificate:
    return x509.load_pem_x509_certificate(certificate_manager.get_ca_certificate())


# --- the mode ---------------------------------------------------------------


def _normalize(value) -> Optional[str]:
    value = (str(value).strip().lower()) if value is not None else ""
    return value if value in MODES else None


def mode_for_host(host_id) -> str:
    """The rollout mode for ``host_id``: its tenant's, else the server's."""
    from backend.config import config, settings_service  # noqa: PLC0415

    tenant_id = None
    if host_id and config.is_multitenancy_enabled():
        try:
            from backend.services import host_tenant_index  # noqa: PLC0415

            tenant_id = host_tenant_index.tenant_for_host(host_id)
        except Exception:  # pylint: disable=broad-exception-caught
            tenant_id = None
    if tenant_id:
        mode = _normalize(settings_service.get_tenant_setting(tenant_id, MODE_SETTING))
        if mode:
            return mode
    return _normalize(settings_service.get_setting(MODE_SETTING)) or DEFAULT_MODE


# --- the decision -----------------------------------------------------------


def _messages() -> dict:
    return {
        CERT_REQUIRED: _(
            "This server requires a client certificate from this host, and none "
            "was presented. The agent requests one automatically; if this "
            "persists, check that the agent is up to date."
        ),
        CERT_INVALID: _(
            "The client certificate this host presented is not valid for it "
            "(not issued by this server, issued to another host, or replaced "
            "or revoked). The connection was refused."
        ),
        CERT_EXPIRED: _(
            "This host's client certificate has expired. The agent requests a "
            "new one automatically."
        ),
    }


def decide(mode: str, verdict: str) -> Decision:
    """Apply the rollout mode to a verdict."""
    if mode == MODE_OFF or verdict == VALID:
        return Decision(True, verdict)
    if verdict in (UNTRUSTED, WRONG_HOST, REVOKED):
        return Decision(False, verdict, CERT_INVALID, _messages()[CERT_INVALID])
    if mode == MODE_ENFORCED:
        code = CERT_EXPIRED if verdict == EXPIRED else CERT_REQUIRED
        return Decision(False, verdict, code, _messages()[code])
    return Decision(True, verdict)


def _note_presented(host, now: datetime) -> bool:
    last = host.certificate_last_presented_at
    if last is not None and now - last < PRESENTED_REFRESH:
        return False
    host.certificate_last_presented_at = now
    return True


def check_host(host, header_value: Optional[str], now=None) -> Decision:
    """Check what a connection for ``host`` presented, under its mode.

    A valid presentation is noted on the row (at most hourly; the caller
    commits) -- that is how the Hosts list shows hosts not yet presenting
    one, before enforcement is turned on."""
    now = now or _naive_utc(datetime.now(timezone.utc))
    cert = presented_certificate(header_value)
    verdict = verdict_for(cert, host, now)
    decision = decide(mode_for_host(getattr(host, "id", None)), verdict)
    if verdict == VALID and host is not None:
        decision.noted = _note_presented(host, now)
    if not decision.allowed:
        logger.warning(
            "Agent connection for host %s refused: client certificate %s",
            sanitize_log(getattr(host, "id", None)),
            verdict,
        )
    return decision


def allow_bootstrap(decision: Decision, host) -> bool:
    """A refusal that is lifted because the host holds no current certificate.

    Enforcement cannot apply to a host that has nothing to present yet -- a
    newly approved one, or one whose certificate expired -- or it could never
    get one.  Such a host proceeds on its host token, logged; the first thing
    its agent does is request a certificate.  A certificate that is presented
    and wrong is never lifted."""
    if decision.allowed or decision.code == CERT_INVALID:
        return False
    if has_current_certificate(host):
        return False
    logger.info(
        "Host %s has no current client certificate; accepted on its host token "
        "so it can get one",
        sanitize_log(getattr(host, "id", None)),
    )
    return True


def has_current_certificate(host, now=None) -> bool:
    """Whether ``host`` holds an unexpired certificate issued by this server."""
    now = now or _naive_utc(datetime.now(timezone.utc))
    expires = getattr(host, "certificate_expires_at", None)
    return bool(host.certificate_serial and expires and expires > now)


# How long a host may go without presenting its certificate before the Hosts
# list says so (agents reconnect and poll far more often than this).
PRESENTED_WINDOW = timedelta(hours=24)

STATUS_NONE = "none"  # no certificate issued
STATUS_EXPIRED = "expired"
STATUS_NOT_PRESENTED = "not_presented"  # issued, but not seen on a connection
STATUS_EXPIRING = "expiring"  # presented; renewal window reached
STATUS_PRESENTING = "presenting"


def certificate_status(host, now=None) -> str:
    """One word for the Hosts list: where this host stands on certificates."""
    now = now or _naive_utc(datetime.now(timezone.utc))
    expires = getattr(host, "certificate_expires_at", None)
    if not getattr(host, "certificate_serial", None) or expires is None:
        return STATUS_NONE
    if expires <= now:
        return STATUS_EXPIRED
    last = getattr(host, "certificate_last_presented_at", None)
    if last is None or now - last > PRESENTED_WINDOW:
        return STATUS_NOT_PRESENTED
    if expires - now <= RENEW_BEFORE:
        return STATUS_EXPIRING
    return STATUS_PRESENTING


# --- issuing from a certificate request -------------------------------------


class CsrRefused(ValueError):
    """A certificate request this server will not sign."""


def _check_csr_key(public_key) -> None:
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        if public_key.curve.name not in ("secp256r1", "secp384r1"):
            raise CsrRefused(_("Unsupported elliptic curve in the request"))
        return
    if isinstance(public_key, rsa.RSAPublicKey):
        if public_key.key_size < 2048:
            raise CsrRefused(_("RSA keys must be at least 2048 bits"))
        return
    raise CsrRefused(_("Unsupported key type in the request"))


def issue_from_csr(host, csr_pem: str, now=None) -> x509.Certificate:
    """Sign a certificate for ``host`` from the agent's request and record it.

    The request's subject is ignored -- the certificate names the host this
    row is -- so the request contributes only its public key, whose possession
    the request's own signature proves.
    """
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode())
    except (ValueError, AttributeError) as exc:
        raise CsrRefused(_("The certificate request could not be read")) from exc
    if not csr.is_signature_valid:
        raise CsrRefused(_("The certificate request's signature is not valid"))
    public_key = csr.public_key()
    _check_csr_key(public_key)
    cert = certificate_manager.issue_client_certificate(
        public_key, host.fqdn, str(host.id)
    )
    now = now or _naive_utc(datetime.now(timezone.utc))
    if host.certificate_serial and host.certificate_serial != str(cert.serial_number):
        host.previous_certificate_serial = host.certificate_serial
    host.client_certificate = cert.public_bytes(serialization.Encoding.PEM).decode()
    host.certificate_serial = str(cert.serial_number)
    host.certificate_issued_at = now
    host.certificate_expires_at = _naive_utc(cert.not_valid_after_utc)
    return cert


# --- the server's identity (pinning) ----------------------------------------


def spki_sha256(cert: x509.Certificate) -> str:
    """Lowercase hex SHA-256 of a certificate's DER SubjectPublicKeyInfo."""
    der = cert.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest()


_spki_cache = {"at": 0.0, "value": []}


def _probe_target():
    """Where nginx serves this console: (connect host, port, SNI name)."""
    from backend.api.password_reset import get_dynamic_hostname  # noqa: PLC0415
    from backend.config import config  # noqa: PLC0415
    from backend.config.public_url import build_public_base_url  # noqa: PLC0415

    split = urlsplit(build_public_base_url(config.get_config(), get_dynamic_hostname))
    if split.scheme != "https" or not split.hostname:
        return None
    # nginx is the only public listener and runs on this host, so ask it on
    # loopback with the public name: what it serves there is what agents see.
    return "127.0.0.1", split.port or 443, split.hostname


def _probe_tls_spki() -> List[str]:
    target = _probe_target()
    if target is None:
        return []
    address, port, server_name = target
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    # Reading our OWN front door's certificate to publish it, not trusting it.
    context.check_hostname = False  # NOSONAR
    context.verify_mode = ssl.CERT_NONE  # NOSONAR
    try:
        with socket.create_connection((address, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=server_name) as tls:
                der = tls.getpeercert(binary_form=True)
    except OSError as exc:
        logger.warning(
            "Could not read the TLS certificate served on %s:%s for %s: %s",
            address,
            port,
            sanitize_log(server_name),
            exc,
        )
        return []
    return [spki_sha256(x509.load_der_x509_certificate(der))] if der else []


def served_tls_spki() -> List[str]:
    """SPKI hashes of the TLS certificate(s) agents are served now.

    ``agent_tls_spki`` (a list, in Settings) overrides the probe for estates
    where the console is served from somewhere this host cannot reach.
    """
    from backend.config import settings_service  # noqa: PLC0415

    configured = settings_service.get_setting("agent_tls_spki")
    if isinstance(configured, list) and configured:
        return [str(item).strip().lower() for item in configured if item]
    if time.monotonic() - _spki_cache["at"] < _SPKI_CACHE_SECONDS:
        return list(_spki_cache["value"])
    value = _probe_tls_spki()
    if value:
        _spki_cache.update(at=time.monotonic(), value=value)
    return value


_PSS = padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH
)


def _sign(key, data: bytes) -> bytes:
    if isinstance(key, rsa.RSAPrivateKey):
        # PSS: nothing deployed checks the older PKCS#1 v1.5 form, so the
        # statement starts with the padding semgrep and CodeQL accept.
        return key.sign(data, _PSS, hashes.SHA256())
    return key.sign(data, ec.ECDSA(hashes.SHA256()))


def identity_document(spki: List[str], now=None) -> dict:
    """The signed statement an agent checks before trusting a new TLS key."""
    certificate_manager.ensure_server_certificate()
    with open(certificate_manager.server_cert_path, "rb") as handle:
        identity_pem = handle.read()
    with open(certificate_manager.server_key_path, "rb") as handle:
        key = serialization.load_pem_private_key(handle.read(), password=None)
    now = now or datetime.now(timezone.utc)
    statement = json.dumps(
        {
            "v": 1,
            "spki_sha256": spki,
            "issued_at": now.isoformat(),
            "expires_at": (now + STATEMENT_LIFETIME).isoformat(),
        },
        separators=(",", ":"),
    ).encode()
    return {
        "ca_certificate": certificate_manager.get_ca_certificate().decode(),
        "identity_certificate": identity_pem.decode(),
        "statement": base64.b64encode(statement).decode(),
        "signature": base64.b64encode(_sign(key, statement)).decode(),
    }
