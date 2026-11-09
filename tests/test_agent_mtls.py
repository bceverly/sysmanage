# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Agent mutual TLS and server pinning, the server half (ROADMAP 25.10).

Certificates here are real: issued by the server's own CA (a temporary one
under pytest) from certificate requests, exactly as agents get them.
"""

import base64
import json
import types
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException

from backend.api import agent_mtls_settings, agent_poll, message_handlers_core
from backend.security import agent_mtls
from backend.security.certificate_manager import certificate_manager


def _now():
    """A moment just after now: certificates issued in a test are valid from
    their issuance, so a time taken before it would read as not yet valid."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=2)


def _host(**fields):
    defaults = {
        "id": uuid.uuid4(),
        "fqdn": "web1.example.com",
        "approval_status": "approved",
        "certificate_serial": None,
        "previous_certificate_serial": None,
        "certificate_issued_at": None,
        "certificate_expires_at": None,
        "certificate_last_presented_at": None,
        "client_certificate": None,
    }
    defaults.update(fields)
    return types.SimpleNamespace(**defaults)


def _csr(key=None, cn="ignored.example.com"):
    key = key or ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def _issued(host):
    """A host with a certificate issued from its own request; the cert."""
    cert = agent_mtls.issue_from_csr(host, _csr(), now=_now())
    return cert


def _header(cert):
    return quote(cert.public_bytes(serialization.Encoding.PEM).decode())


@pytest.fixture(autouse=True)
def _mode(monkeypatch):
    """Each test sets the mode it needs; optional unless it says otherwise."""
    state = {"mode": agent_mtls.MODE_OPTIONAL}
    monkeypatch.setattr(agent_mtls, "mode_for_host", lambda _host_id: state["mode"])
    return state


# --- issuing from a request -------------------------------------------------


def test_the_certificate_names_the_host_not_the_request():
    host = _host()
    cert = _issued(host)
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    ou = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value
    assert cn == "web1.example.com" and ou == str(host.id)
    assert host.certificate_serial == str(cert.serial_number)
    assert host.certificate_expires_at > _now() + timedelta(days=360)
    cert.verify_directly_issued_by(
        x509.load_pem_x509_certificate(certificate_manager.get_ca_certificate())
    )


def test_a_long_host_name_is_cut_in_the_common_name_and_kept_in_the_san():
    """X.509 allows 64 characters in a common name; a host's name can be
    longer, and its certificate must still be issued."""
    fqdn = ("a" * 60) + ".lab.example.com"
    cert = _issued(_host(fqdn=fqdn))
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    assert cn == fqdn[:64]
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert san.value.get_values_for_type(x509.DNSName) == [fqdn]


def test_a_renewal_keeps_the_replaced_serial():
    host = _host()
    first = _issued(host)
    _issued(host)
    assert host.previous_certificate_serial == str(first.serial_number)


@pytest.mark.parametrize(
    "csr",
    [
        "not a request",
        _csr(rsa.generate_private_key(public_exponent=65537, key_size=1024)),
        _csr(ec.generate_private_key(ec.SECP192R1())),
    ],
    ids=["unreadable", "rsa-1024", "p-192"],
)
def test_unusable_requests_are_refused(csr):
    with pytest.raises(agent_mtls.CsrRefused):
        agent_mtls.issue_from_csr(_host(), csr)


# --- verdicts ---------------------------------------------------------------


def test_verdicts():
    host = _host()
    cert = _issued(host)
    assert agent_mtls.verdict_for(None, host) == agent_mtls.NONE
    assert agent_mtls.verdict_for(cert, host, _now()) == agent_mtls.VALID
    assert agent_mtls.verdict_for(cert, _host(), _now()) == agent_mtls.WRONG_HOST
    assert (
        agent_mtls.verdict_for(cert, host, _now() + timedelta(days=400))
        == agent_mtls.EXPIRED
    )


def test_a_certificate_from_another_ca_is_untrusted():
    key = ec.generate_private_key(ec.SECP256R1())
    host = _host()
    forged = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, host.fqdn),
                    x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, str(host.id)),
                ]
            )
        )
        # The SysManage CA's NAME, signed by another key: the issuer-name
        # comparison this replaced would have accepted it.
        .issuer_name(
            x509.load_pem_x509_certificate(
                certificate_manager.get_ca_certificate()
            ).subject
        )
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    assert agent_mtls.verdict_for(forged, host) == agent_mtls.UNTRUSTED


def test_a_replaced_certificate_is_revoked_after_a_day():
    host = _host()
    old = _issued(host)
    _issued(host)
    assert (
        agent_mtls.verdict_for(old, host, _now() + timedelta(hours=1))
        == agent_mtls.VALID
    )
    assert (
        agent_mtls.verdict_for(old, host, _now() + timedelta(days=2))
        == agent_mtls.REVOKED
    )
    host.previous_certificate_serial = None  # an administrator's revoke
    assert agent_mtls.verdict_for(old, host, _now()) == agent_mtls.REVOKED


# --- the modes --------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,verdict,allowed",
    [
        ("off", agent_mtls.WRONG_HOST, True),
        ("optional", agent_mtls.NONE, True),
        ("optional", agent_mtls.EXPIRED, True),
        ("optional", agent_mtls.WRONG_HOST, False),
        ("optional", agent_mtls.UNTRUSTED, False),
        ("optional", agent_mtls.REVOKED, False),
        ("enforced", agent_mtls.NONE, False),
        ("enforced", agent_mtls.EXPIRED, False),
        ("enforced", agent_mtls.VALID, True),
    ],
)
def test_decide(mode, verdict, allowed):
    assert agent_mtls.decide(mode, verdict).allowed is allowed


def test_enforced_refusals_name_what_is_missing():
    assert (
        agent_mtls.decide("enforced", agent_mtls.NONE).code == agent_mtls.CERT_REQUIRED
    )
    assert (
        agent_mtls.decide("enforced", agent_mtls.EXPIRED).code
        == agent_mtls.CERT_EXPIRED
    )
    assert (
        agent_mtls.decide("optional", agent_mtls.REVOKED).code
        == agent_mtls.CERT_INVALID
    )


def test_a_valid_presentation_is_noted_at_most_hourly():
    host = _host()
    cert = _issued(host)
    moment = _now()
    first = agent_mtls.check_host(host, _header(cert), moment)
    assert first.allowed and first.noted
    assert host.certificate_last_presented_at == moment
    again = agent_mtls.check_host(host, _header(cert), moment + timedelta(minutes=5))
    assert not again.noted


# --- REST enforcement -------------------------------------------------------


def _request(header=None):
    headers = {agent_mtls.CLIENT_CERT_HEADER: header} if header else {}
    return types.SimpleNamespace(headers=headers)


class _Db:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_enforced_rest_refuses_a_host_without_its_certificate(_mode):
    _mode["mode"] = agent_mtls.MODE_ENFORCED
    host = _host()
    _issued(host)
    with pytest.raises(HTTPException) as refused:
        agent_poll._check_certificate(_Db(), host, _request(), False)
    assert refused.value.status_code == 403
    assert refused.value.detail["code"] == agent_mtls.CERT_REQUIRED


def test_enforced_rest_accepts_the_hosts_certificate(_mode):
    _mode["mode"] = agent_mtls.MODE_ENFORCED
    host = _host()
    cert = _issued(host)
    db = _Db()
    agent_poll._check_certificate(db, host, _request(_header(cert)), False)
    assert db.commits == 1  # the presentation was noted


def test_another_hosts_certificate_is_refused_even_when_optional():
    owner = _host()
    cert = _issued(owner)
    other = _host(fqdn="db1.example.com")
    _issued(other)
    with pytest.raises(HTTPException) as refused:
        agent_poll._check_certificate(_Db(), other, _request(_header(cert)), True)
    assert refused.value.detail["code"] == agent_mtls.CERT_INVALID


def test_the_certificate_endpoint_bootstraps_a_host_with_none(_mode):
    _mode["mode"] = agent_mtls.MODE_ENFORCED
    agent_poll._check_certificate(_Db(), _host(), _request(), True)  # no raise


def test_bootstrap_does_not_cover_a_host_with_a_current_certificate(_mode):
    _mode["mode"] = agent_mtls.MODE_ENFORCED
    host = _host()
    _issued(host)
    with pytest.raises(HTTPException):
        agent_poll._check_certificate(_Db(), host, _request(), True)


# --- WebSocket enforcement --------------------------------------------------


def test_the_websocket_refuses_an_enforced_host_without_its_certificate(
    _mode, monkeypatch
):
    _mode["mode"] = agent_mtls.MODE_ENFORCED
    monkeypatch.setattr(message_handlers_core.AuditService, "log", lambda **_kw: None)
    host = _host()
    _issued(host)
    connection = types.SimpleNamespace(client_cert_header=None)
    claim = types.SimpleNamespace(host=host)
    reply = message_handlers_core._certificate_refusal(_Db(), connection, claim)
    assert reply["message_type"] == "error"
    assert reply["error_type"] == agent_mtls.CERT_REQUIRED


def test_the_websocket_lets_a_pending_host_through(_mode):
    _mode["mode"] = agent_mtls.MODE_ENFORCED
    claim = types.SimpleNamespace(host=_host(approval_status="pending"))
    connection = types.SimpleNamespace(client_cert_header=None)
    assert message_handlers_core._certificate_refusal(_Db(), connection, claim) is None


# --- the Hosts list ---------------------------------------------------------


def test_certificate_status():
    host = _host()
    assert agent_mtls.certificate_status(host, _now()) == agent_mtls.STATUS_NONE
    _issued(host)
    assert (
        agent_mtls.certificate_status(host, _now()) == agent_mtls.STATUS_NOT_PRESENTED
    )
    host.certificate_last_presented_at = _now()
    assert agent_mtls.certificate_status(host, _now()) == agent_mtls.STATUS_PRESENTING
    later = host.certificate_expires_at - timedelta(days=10)
    host.certificate_last_presented_at = later
    assert agent_mtls.certificate_status(host, later) == agent_mtls.STATUS_EXPIRING
    gone = host.certificate_expires_at + timedelta(days=1)
    assert agent_mtls.certificate_status(host, gone) == agent_mtls.STATUS_EXPIRED


# --- the server's signed identity -------------------------------------------


def test_the_identity_statement_is_signed_by_a_certificate_from_the_ca():
    document = agent_mtls.identity_document(["ab" * 32])
    ca = x509.load_pem_x509_certificate(document["ca_certificate"].encode())
    identity = x509.load_pem_x509_certificate(document["identity_certificate"].encode())
    identity.verify_directly_issued_by(ca)
    statement = base64.b64decode(document["statement"])
    signature = base64.b64decode(document["signature"])
    key = identity.public_key()
    if isinstance(key, rsa.RSAPublicKey):
        key.verify(signature, statement, padding.PKCS1v15(), hashes.SHA256())
    else:
        key.verify(signature, statement, ec.ECDSA(hashes.SHA256()))
    body = json.loads(statement)
    assert body["v"] == 1 and body["spki_sha256"] == ["ab" * 32]
    assert datetime.fromisoformat(body["expires_at"]) > datetime.now(timezone.utc)


def test_configured_spki_overrides_the_probe(monkeypatch):
    from backend.config import settings_service  # noqa: PLC0415

    monkeypatch.setattr(
        settings_service,
        "get_setting",
        lambda key, *a, **k: ["AA" * 32] if key == "agent_tls_spki" else None,
    )
    monkeypatch.setattr(
        agent_mtls, "_probe_tls_spki", lambda: pytest.fail("probed anyway")
    )
    assert agent_mtls.served_tls_spki() == ["aa" * 32]


# --- the enforce guard ------------------------------------------------------


def _fleet(not_presenting):
    return agent_mtls_settings.FleetStatus(
        approved=3, presenting=3 - not_presenting, not_presenting=not_presenting,
        expiring=0, expired=0, not_ready=[],
    )  # fmt: skip


@pytest.mark.asyncio
async def test_enforcing_with_hosts_not_ready_needs_confirmation(monkeypatch):
    stored = {}
    monkeypatch.setattr(agent_mtls_settings, "_fleet", lambda: _fleet(2))
    monkeypatch.setattr(agent_mtls_settings, "_tenant", lambda: None)
    monkeypatch.setattr(
        agent_mtls_settings.settings_service, "set_setting",
        lambda key, value: stored.update({key: value}),
    )  # fmt: skip
    monkeypatch.setattr(agent_mtls_settings, "_current", lambda: "current")
    with pytest.raises(HTTPException) as refused:
        await agent_mtls_settings.update_agent_certificates(
            agent_mtls_settings.MtlsUpdate(mode="enforced"), user="ops"
        )
    assert refused.value.status_code == 409
    assert refused.value.detail["count"] == 2 and not stored
    await agent_mtls_settings.update_agent_certificates(
        agent_mtls_settings.MtlsUpdate(mode="enforced", force=True), user="ops"
    )
    assert stored == {agent_mtls.MODE_SETTING: "enforced"}


@pytest.mark.asyncio
async def test_an_unknown_mode_is_refused():
    with pytest.raises(HTTPException) as refused:
        await agent_mtls_settings.update_agent_certificates(
            agent_mtls_settings.MtlsUpdate(mode="strict"), user="ops"
        )
    assert refused.value.status_code == 422
