# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy's certificate from the SysManage CA (ROADMAP 25.5).

The storage host makes the key and sends a request; the server signs it for
the target's proxy name, keeps the certificate and sends it back; hosts trust
it through the SysManage CA.  An operator's own CA wins.
"""

# pylint: disable=redefined-outer-name

import json

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from backend.security.certificate_manager import certificate_manager
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_proxy_cert as proxy_cert
from backend.services import backup_reach as reach
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)
from tests.test_agent_mtls import P192_CSR

CAPTURES = ("list", proxy.REMOTE_ABILITY, proxy.REMOTE_CAPTURE)


def _on_proxy(session, host="backup.example.lan"):
    s = _setup(session)
    s.target.transport = proxy.PROXY
    s.target.proxy_host = host
    s.target.proxy_port = 8443
    s.policy.host_abilities = json.dumps(list(CAPTURES))
    session.commit()
    return s


def _csr(name="anything-the-host-likes"):
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .sign(key, hashes.SHA256())
    )
    return key, csr.public_bytes(serialization.Encoding.PEM).decode()


def _storage_cert(session, s, sent):
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    return sent[-1][2]["target"]["proxy"].get("cert")


def test_the_storage_host_is_asked_for_a_request(session, sent):
    s = _on_proxy(session)
    assert _storage_cert(session, s, sent) == {
        "name": "backup.example.lan", "pem": None, "renew": True
    }  # fmt: skip


def test_its_request_is_signed_for_the_targets_name_only(session):
    s = _on_proxy(session)
    key, csr = _csr("evil.example.com")
    before = s.policy.config_version
    assert proxy_cert.store_csr(session, s.policy, {"proxy_csr": csr})
    cert = x509.load_pem_x509_certificate(s.target.proxy_cert_pem.encode())
    alt = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert alt.get_values_for_type(x509.DNSName) == ["backup.example.lan"]
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert list(eku) == [ExtendedKeyUsageOID.SERVER_AUTH]
    ca = x509.load_pem_x509_certificate(certificate_manager.get_ca_certificate())
    cert.verify_directly_issued_by(ca)
    assert cert.public_key().public_numbers() == key.public_key().public_numbers()
    assert s.policy.config_version > before  # the storage host gets it now


def test_once_issued_it_is_sent_and_hosts_trust_the_sysmanage_ca(session, sent):
    s = _on_proxy(session)
    proxy_cert.store_csr(session, s.policy, {"proxy_csr": _csr()[1]})
    got = _storage_cert(session, s, sent)
    assert got["renew"] is False and got["pem"] == s.target.proxy_cert_pem
    ca = certificate_manager.get_ca_certificate().decode()
    host = jobs.host_configuration(s.policy, s.target, s.host)["target"]["proxy"]
    assert host["ca"] == ca
    assert reach.storage_address(session)["proxy"]["ca"] == ca
    assert proxy.target_view(s.target)["certificate"]["current"] is True


def test_the_same_request_again_is_ignored_while_the_certificate_serves(session):
    # A storage host with several policies asks in each configure reply.
    s = _on_proxy(session)
    csr = _csr()[1]
    proxy_cert.store_csr(session, s.policy, {"proxy_csr": csr})
    issued = s.target.proxy_cert_pem
    assert not proxy_cert.store_csr(session, s.policy, {"proxy_csr": csr})
    assert s.target.proxy_cert_pem == issued


def test_a_request_with_another_key_is_issued_again(session):
    # The storage host lost the key the certificate is for: it must get one
    # for the key it has, or its proxy could never start.
    s = _on_proxy(session)
    proxy_cert.store_csr(session, s.policy, {"proxy_csr": _csr()[1]})
    first = s.target.proxy_cert_pem
    key, csr = _csr()
    assert proxy_cert.store_csr(session, s.policy, {"proxy_csr": csr})
    cert = x509.load_pem_x509_certificate(s.target.proxy_cert_pem.encode())
    assert s.target.proxy_cert_pem != first
    assert cert.public_key().public_numbers() == key.public_key().public_numbers()


def test_a_new_proxy_address_wants_a_new_certificate(session, sent):
    s = _on_proxy(session)
    proxy_cert.store_csr(session, s.policy, {"proxy_csr": _csr()[1]})
    s.target.proxy_host = "192.168.4.10"
    session.commit()
    assert _storage_cert(session, s, sent) == {
        "name": "192.168.4.10", "pem": None, "renew": True
    }  # fmt: skip
    proxy_cert.store_csr(session, s.policy, {"proxy_csr": _csr()[1]})
    cert = x509.load_pem_x509_certificate(s.target.proxy_cert_pem.encode())
    alt = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert [str(ip) for ip in alt.get_values_for_type(x509.IPAddress)] == [
        "192.168.4.10"
    ]


def test_a_weak_or_unreadable_request_is_refused(session):
    s = _on_proxy(session)
    for bad in (P192_CSR, "not a request", 42):
        assert not proxy_cert.store_csr(session, s.policy, {"proxy_csr": bad})
    assert s.target.proxy_cert_pem is None


def test_an_operators_own_ca_wins(session, sent):
    from tests.test_backup_proxy_ca import ca_pem  # noqa: PLC0415

    s = _on_proxy(session)
    s.target.proxy_ca_pem = ca_pem()
    session.commit()
    assert _storage_cert(session, s, sent) is None
    assert not proxy_cert.store_csr(session, s.policy, {"proxy_csr": _csr()[1]})
    host = jobs.host_configuration(s.policy, s.target, s.host)["target"]["proxy"]
    assert host["ca"] == s.target.proxy_ca_pem


def test_an_nfs_target_gets_no_certificate(session, sent):
    s = _setup(session)
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert "cert" not in sent[-1][2]["target"]["proxy"]
    assert not proxy_cert.store_csr(session, s.policy, {"proxy_csr": _csr()[1]})


def test_equip_tells_only_a_proxy_targets_storage_host_to_add_the_proxy(session):
    from backend.services import backup_equip  # noqa: PLC0415

    s = _on_proxy(session)
    assert backup_equip.parameters(session, s.nas) == {"proxy": True}
    assert backup_equip.parameters(session, s.host) == {}  # a backed-up host
    s.target.transport = proxy.NFS
    session.commit()
    assert backup_equip.parameters(session, s.nas) == {}
