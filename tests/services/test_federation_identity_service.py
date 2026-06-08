"""
Tests for the Phase 12 federation identity-key service (Server Role UI):
keypair generation, public-key/fingerprint access, and the trusted-peer
keyring (import / list / remove) — the federation mirror of the air-gap
collector key exchange.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,redefined-outer-name

import os

import pytest

from backend.services import federation_identity_service as fid


@pytest.fixture
def keydirs(tmp_path, monkeypatch):
    key_file = str(tmp_path / "id" / "identity-ed25519.pem")
    peer_dir = str(tmp_path / "peers")
    monkeypatch.setattr(
        "backend.config.config.get_federation_identity_key_file", lambda: key_file
    )
    monkeypatch.setattr(
        "backend.config.config.get_federation_peer_public_key_dir", lambda: peer_dir
    )
    cert_file = str(tmp_path / "id" / "identity-cert.pem")
    monkeypatch.setattr(
        "backend.config.config.get_federation_tls_cert_file", lambda: cert_file
    )
    return key_file, peer_dir


class TestTlsCert:
    def test_ensure_creates_cert_and_key_with_modes(self, keydirs, tmp_path):
        cert, key = fid.ensure_federation_tls_cert()
        assert os.path.isfile(cert) and os.path.isfile(key)
        assert cert == str(tmp_path / "id" / "identity-cert.pem")
        assert key == str(tmp_path / "id" / "identity-cert-key.pem")
        assert oct(os.stat(cert).st_mode)[-3:] == "644"
        assert oct(os.stat(key).st_mode)[-3:] == "600"

    def test_cert_pem_is_a_valid_x509_certificate(self, keydirs):
        pem = fid.get_federation_tls_cert_pem()
        assert pem and "BEGIN CERTIFICATE" in pem
        from cryptography import x509  # pylint: disable=import-outside-toplevel

        assert x509.load_pem_x509_certificate(pem.encode("utf-8")) is not None

    def test_ensure_is_idempotent_and_never_overwrites(self, keydirs):
        cert, _key = fid.ensure_federation_tls_cert()
        with open(cert, "rb") as fh:
            first = fh.read()
        fid.ensure_federation_tls_cert()
        with open(cert, "rb") as fh:
            assert fh.read() == first


class TestIdentityKeypair:
    def test_ensure_creates_private_and_public(self, keydirs):
        key_file, _peer = keydirs
        priv, pub = fid.ensure_federation_identity_keypair()
        assert os.path.isfile(priv) and os.path.isfile(pub)
        assert priv == key_file
        # 0600 private, 0644 public.
        assert oct(os.stat(priv).st_mode)[-3:] == "600"
        assert oct(os.stat(pub).st_mode)[-3:] == "644"

    def test_ensure_is_idempotent_and_never_overwrites(self, keydirs):
        priv, _pub = fid.ensure_federation_identity_keypair()
        with open(priv, "rb") as fh:
            first = fh.read()
        fid.ensure_federation_identity_keypair()  # second call
        with open(priv, "rb") as fh:
            second = fh.read()
        assert second == first  # untouched

    def test_public_key_auto_creates_on_first_read(self, keydirs):
        # No ensure() call first — the getter mints the keypair.
        pem = fid.get_federation_identity_public_key_pem()
        assert pem and "PUBLIC KEY" in pem

    def test_fingerprint_is_sha256_hex(self, keydirs):
        fp = fid.get_federation_identity_public_key_fingerprint()
        assert fp and len(fp) == 64 and all(c in "0123456789abcdef" for c in fp)

    def test_rederives_public_if_deleted(self, keydirs):
        priv, pub = fid.ensure_federation_identity_keypair()
        os.unlink(pub)
        fid.ensure_federation_identity_keypair()
        assert os.path.isfile(pub)


class TestPeerKeyring:
    def _a_peer_pem(self, keydirs):
        # Generate a SECOND keypair to use as a "peer" key.
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        pub = Ed25519PrivateKey.generate().public_key()
        return pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def test_import_then_list_then_remove(self, keydirs):
        pem = self._a_peer_pem(keydirs)
        result = fid.import_federation_peer("Site Alpha!", pem)
        assert result["name"] == "Site-Alpha"  # slugified
        assert len(result["fingerprint"]) == 64

        peers = fid.list_federation_peers()
        assert len(peers) == 1 and peers[0]["name"] == "Site-Alpha"

        assert fid.remove_federation_peer("Site-Alpha") is True
        assert fid.list_federation_peers() == []

    def test_import_rejects_non_ed25519(self, keydirs):
        with pytest.raises(ValueError):
            fid.import_federation_peer(
                "bad", "-----BEGIN PUBLIC KEY-----\nnope\n-----END PUBLIC KEY-----\n"
            )

    def test_import_dedups_whitespace_to_same_fingerprint(self, keydirs):
        pem = self._a_peer_pem(keydirs)
        r1 = fid.import_federation_peer("p", pem)
        # Re-import the same key with extra blank lines — same fingerprint.
        r2 = fid.import_federation_peer("p", "\n\n" + pem + "\n")
        assert r1["fingerprint"] == r2["fingerprint"]

    def test_remove_missing_returns_false(self, keydirs):
        assert fid.remove_federation_peer("nope") is False


class TestWireSigning:
    def test_sign_then_verify_roundtrip(self, keydirs):
        body = b'{"hello":"world"}'
        sig = fid.sign_federation_request(body)
        assert sig
        cert_pem = fid.get_federation_tls_cert_pem()
        assert fid.verify_federation_request(body, sig, cert_pem) is True

    def test_tampered_body_fails(self, keydirs):
        sig = fid.sign_federation_request(b'{"hello":"world"}')
        cert_pem = fid.get_federation_tls_cert_pem()
        assert fid.verify_federation_request(b'{"hello":"x"}', sig, cert_pem) is False

    def test_wrong_cert_fails(self, keydirs):
        sig = fid.sign_federation_request(b"payload")
        # A different self-signed cert (different key) must not verify.
        from cryptography import x509  # pylint: disable=import-outside-toplevel
        from cryptography.hazmat.primitives import (  # pylint: disable=import-outside-toplevel
            hashes,
            serialization,
        )
        from cryptography.hazmat.primitives.asymmetric import (  # pylint: disable=import-outside-toplevel
            rsa,
        )
        from cryptography.x509.oid import (  # pylint: disable=import-outside-toplevel
            NameOID,
        )
        import datetime  # pylint: disable=import-outside-toplevel

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "other")])
        now = datetime.datetime.now(datetime.timezone.utc)
        other = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        other_pem = other.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        assert fid.verify_federation_request(b"payload", sig, other_pem) is False

    def test_empty_inputs_fail_closed(self, keydirs):
        assert fid.verify_federation_request(b"x", "", "cert") is False
        assert fid.verify_federation_request(b"x", "sig", "") is False
