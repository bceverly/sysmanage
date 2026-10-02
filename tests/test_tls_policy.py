# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The server's TLS offers no CBC cipher suites (Lucky Thirteen, CVE-2013-0169).

Found 2026-10-02: uvicorn's default cipher string ("TLSv1") and nginx's
default ("HIGH:!aNULL:!MD5") both offered CBC suites.  These make REAL
handshakes against the exact SSL context uvicorn builds from our arguments,
and hold every installer's nginx config to the same list.
"""

import datetime
import re
import socket
import ssl
import threading
from pathlib import Path

import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend.security.tls_policy import SERVER_CIPHERS, uvicorn_tls_kwargs

REPO = Path(__file__).resolve().parents[1]
CBC_SUITES = ("ECDHE-RSA-AES128-SHA", "ECDHE-RSA-AES256-SHA384", "AES128-SHA")


def _is_aead(name: str) -> bool:
    return "GCM" in name or "CHACHA20" in name or name.startswith("TLS_")


@pytest.fixture(scope="module")
def cert_files(tmp_path_factory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )  # fmt: skip
    folder = tmp_path_factory.mktemp("tls")
    key_file, cert_file = folder / "server.key", folder / "server.crt"
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                           serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))  # fmt: skip
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(key_file), str(cert_file)


@pytest.fixture(scope="module")
def server_port(cert_files):
    """A TLS listener using the SSL context uvicorn builds from our kwargs."""
    key_file, cert_file = cert_files
    config = uvicorn.Config(lambda *_: None, **uvicorn_tls_kwargs(key_file, cert_file))
    config.load()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    stop = threading.Event()

    def serve():
        listener.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            try:
                with config.ssl.wrap_socket(conn, server_side=True) as tls:
                    tls.recv(1)
            except (ssl.SSLError, OSError):
                # A refused handshake is what the CBC tests expect; the
                # client side asserts it.  Keep serving.
                continue

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield listener.getsockname()[1]
    stop.set()
    thread.join(timeout=2)
    listener.close()


def _handshake(port, ciphers=None, maximum=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if ciphers:
        context.set_ciphers(ciphers)
    if maximum:
        context.maximum_version = maximum
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname="localhost") as tls:
            name = tls.cipher()[0]
            tls.sendall(b"x")
            return name


def test_the_policy_is_aead_only():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.set_ciphers(SERVER_CIPHERS)
    offered = [cipher["name"] for cipher in context.get_ciphers()]
    assert offered and all(_is_aead(name) for name in offered), offered


def test_uvicorn_gets_the_policy():
    assert uvicorn_tls_kwargs("k", "c")["ssl_ciphers"] == SERVER_CIPHERS
    assert uvicorn_tls_kwargs("k", "c", "chain")["ssl_ca_certs"] == "chain"


@pytest.mark.parametrize("suite", CBC_SUITES)
def test_a_cbc_suite_is_refused(server_port, suite):
    try:
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).set_ciphers(suite)
    except ssl.SSLError:
        pytest.skip(f"this OpenSSL cannot offer {suite}")
    with pytest.raises((ssl.SSLError, ConnectionError)):
        _handshake(server_port, ciphers=suite, maximum=ssl.TLSVersion.TLSv1_2)


def test_tls_1_2_negotiates_aead(server_port):
    assert _is_aead(_handshake(server_port, maximum=ssl.TLSVersion.TLSv1_2))


def test_tls_1_3_still_works(server_port):
    assert _is_aead(_handshake(server_port))


def test_every_nginx_config_carries_the_same_list():
    configs = sorted(REPO.glob("installer/*/sysmanage-nginx.conf"))
    configs.append(
        REPO
        / "packaging/freebsd-ports/sysutils/sysmanage/files/sysmanage-nginx.conf.in"
    )
    assert len(configs) >= 10
    for path in configs:
        found = re.findall(r"^\s*ssl_ciphers\s+([^;]+);", path.read_text(), re.M)
        assert found == [SERVER_CIPHERS], path
