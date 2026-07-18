# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for ``backend/services/airgap_signing_service.py``.

Exercises the zero-touch collector keypair lifecycle and the
repository-side trusted-collector keyring entirely against a temp
directory — no real /etc paths are touched.  Config accessors
(``get_airgap_signing_key_file`` / ``get_airgap_collector_public_key_dir``)
are monkeypatched to point inside ``tmp_path``.
"""

# pylint: disable=missing-function-docstring,redefined-outer-name

import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

from backend.services import airgap_signing_service as svc


@pytest.fixture
def signing_paths(tmp_path, monkeypatch):
    """Point the collector private key + keyring dir inside tmp_path."""
    private_path = str(tmp_path / "keys" / "collector_signing_key.pem")
    keyring_dir = str(tmp_path / "trusted_collectors")
    monkeypatch.setattr(
        svc.config_module, "get_airgap_signing_key_file", lambda: private_path
    )
    monkeypatch.setattr(
        svc.config_module,
        "get_airgap_collector_public_key_dir",
        lambda: keyring_dir,
    )
    return private_path, keyring_dir


def _make_public_pem() -> str:
    key = Ed25519PrivateKey.generate()
    return (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )


# ---------------------------------------------------------------------
# ensure_collector_keypair
# ---------------------------------------------------------------------


class TestEnsureCollectorKeypair:
    def test_generates_keypair_on_first_call(self, signing_paths):
        private_path, _ = signing_paths
        priv, pub = svc.ensure_collector_keypair()
        assert priv == private_path
        assert pub == svc._public_key_path(private_path)
        assert os.path.isfile(priv)
        assert os.path.isfile(pub)
        # Private key is a valid, loadable ed25519 PEM.
        with open(priv, "rb") as fh:
            loaded = serialization.load_pem_private_key(fh.read(), password=None)
        assert isinstance(loaded, Ed25519PrivateKey)

    def test_private_key_is_0600(self, signing_paths):
        priv, _ = svc.ensure_collector_keypair()
        mode = os.stat(priv).st_mode & 0o777
        assert mode == 0o600

    def test_idempotent_never_overwrites_private(self, signing_paths):
        priv, _ = svc.ensure_collector_keypair()
        with open(priv, "rb") as fh:
            first = fh.read()
        # Second call must not regenerate.
        svc.ensure_collector_keypair()
        with open(priv, "rb") as fh:
            second = fh.read()
        assert first == second

    def test_rederives_public_when_pub_deleted(self, signing_paths):
        priv, pub = svc.ensure_collector_keypair()
        os.unlink(pub)
        assert not os.path.isfile(pub)
        svc.ensure_collector_keypair()
        assert os.path.isfile(pub)


# ---------------------------------------------------------------------
# get_collector_private_key_pem / get_collector_public_key_pem
# ---------------------------------------------------------------------


class TestGetKeyPem:
    def test_private_pem_none_when_absent(self, signing_paths):
        assert svc.get_collector_private_key_pem() is None

    def test_private_pem_read_after_generate(self, signing_paths):
        svc.ensure_collector_keypair()
        pem = svc.get_collector_private_key_pem()
        assert pem is not None
        assert "PRIVATE KEY" in pem

    def test_public_pem_read_after_generate(self, signing_paths):
        svc.ensure_collector_keypair()
        pem = svc.get_collector_public_key_pem()
        assert pem is not None
        assert "PUBLIC KEY" in pem

    def test_public_pem_rederives_when_missing(self, signing_paths):
        priv, pub = svc.ensure_collector_keypair()
        os.unlink(pub)
        # get should re-derive it via ensure_collector_keypair().
        pem = svc.get_collector_public_key_pem()
        assert pem is not None
        assert os.path.isfile(pub)

    def test_public_pem_none_when_nothing_exists(self, signing_paths):
        # No private key at all — re-derive attempt still yields a fresh pair,
        # so a PEM comes back (ensure_collector_keypair generates it).
        pem = svc.get_collector_public_key_pem()
        assert pem is not None


# ---------------------------------------------------------------------
# fingerprints
# ---------------------------------------------------------------------


class TestFingerprints:
    def test_fingerprint_is_stable_across_whitespace(self):
        pem = _make_public_pem()
        noisy = "\n\n" + pem + "\n  \n"
        assert svc.fingerprint_of_public_pem(pem) == svc.fingerprint_of_public_pem(
            noisy
        )

    def test_fingerprint_accepts_bytes(self):
        pem = _make_public_pem()
        assert svc.fingerprint_of_public_pem(pem) == svc.fingerprint_of_public_pem(
            pem.encode("utf-8")
        )

    def test_fingerprint_is_64_hex_chars(self):
        fp = svc.fingerprint_of_public_pem(_make_public_pem())
        assert len(fp) == 64
        int(fp, 16)  # parses as hex

    def test_non_ed25519_public_key_raises(self):
        rsa_pub = (
            generate_private_key(public_exponent=65537, key_size=2048)
            .public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )
        with pytest.raises(ValueError):
            svc.fingerprint_of_public_pem(rsa_pub)

    def test_server_public_fingerprint_after_generate(self, signing_paths):
        svc.ensure_collector_keypair()
        fp = svc.get_collector_public_key_fingerprint()
        assert fp is not None
        assert len(fp) == 64

    def test_server_public_fingerprint_none_when_no_key(
        self, signing_paths, monkeypatch
    ):
        monkeypatch.setattr(svc, "get_collector_public_key_pem", lambda: None)
        assert svc.get_collector_public_key_fingerprint() is None

    def test_server_public_fingerprint_none_on_bad_pem(
        self, signing_paths, monkeypatch
    ):
        monkeypatch.setattr(svc, "get_collector_public_key_pem", lambda: "not-a-pem")
        assert svc.get_collector_public_key_fingerprint() is None


# ---------------------------------------------------------------------
# name slugging + path containment
# ---------------------------------------------------------------------


class TestNameSlug:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("simple", "simple"),
            ("with spaces", "with-spaces"),
            ("../escape", "escape"),
            # '.' and '-' are in the allowed charset; only the '/' run is
            # collapsed to a single '-'.
            ("weird/../name", "weird-..-name"),
            ("", "collector"),
            ("   ", "collector"),
            ("!!!", "collector"),
            ("Site-A_01.pub", "Site-A_01.pub"),
        ],
    )
    def test_safe_key_name(self, raw, expected):
        assert svc._safe_key_name(raw) == expected

    def test_keyring_path_contained(self, tmp_path):
        base = str(tmp_path)
        p = svc._keyring_key_path(base, "site-a")
        assert p.startswith(base + os.sep)
        assert p.endswith("site-a.pub")

    def test_keyring_path_traversal_slugged_away(self, tmp_path):
        # "../../etc/passwd" gets slugged to a tame name that stays contained.
        base = str(tmp_path)
        p = svc._keyring_key_path(base, "../../etc/passwd")
        assert p.startswith(base + os.sep)


# ---------------------------------------------------------------------
# trusted-collector keyring: import / list / remove
# ---------------------------------------------------------------------


class TestTrustedKeyring:
    def test_list_empty_when_dir_missing(self, signing_paths):
        assert svc.list_trusted_collectors() == []

    def test_import_then_list(self, signing_paths):
        pem = _make_public_pem()
        rec = svc.import_trusted_collector("Site A", pem)
        assert rec["name"] == "Site-A"
        assert len(rec["fingerprint"]) == 64

        listed = svc.list_trusted_collectors()
        assert len(listed) == 1
        assert listed[0]["name"] == "Site-A"
        assert listed[0]["fingerprint"] == rec["fingerprint"]

    def test_import_bad_key_raises(self, signing_paths):
        with pytest.raises(ValueError):
            svc.import_trusted_collector("bad", "definitely not a pem")

    def test_import_canonicalizes(self, signing_paths):
        pem = _make_public_pem()
        rec1 = svc.import_trusted_collector("noisy", "\n" + pem + "\n\n")
        # Fingerprint matches the canonical fingerprint of the clean PEM.
        assert rec1["fingerprint"] == svc.fingerprint_of_public_pem(pem)

    def test_list_skips_non_pem_files(self, signing_paths):
        _, keyring_dir = signing_paths
        svc.import_trusted_collector("good", _make_public_pem())
        # Drop a garbage file into the keyring — it should be listed with
        # fingerprint None, not crash.
        os.makedirs(keyring_dir, exist_ok=True)
        with open(os.path.join(keyring_dir, "junk.pub"), "w", encoding="utf-8") as fh:
            fh.write("garbage")
        listed = {r["name"]: r["fingerprint"] for r in svc.list_trusted_collectors()}
        assert listed["good"] is not None
        assert listed["junk"] is None

    def test_list_ignores_subdirectories(self, signing_paths):
        _, keyring_dir = signing_paths
        os.makedirs(os.path.join(keyring_dir, "a_subdir"), exist_ok=True)
        svc.import_trusted_collector("real", _make_public_pem())
        names = [r["name"] for r in svc.list_trusted_collectors()]
        assert "real" in names
        assert "a_subdir" not in names

    def test_remove_returns_true_and_deletes(self, signing_paths):
        svc.import_trusted_collector("gone", _make_public_pem())
        assert svc.remove_trusted_collector("gone") is True
        assert svc.list_trusted_collectors() == []

    def test_remove_missing_returns_false(self, signing_paths):
        svc.import_trusted_collector("keep", _make_public_pem())
        assert svc.remove_trusted_collector("never-existed") is False
        # The existing key is untouched.
        assert len(svc.list_trusted_collectors()) == 1

    def test_import_written_0644(self, signing_paths):
        _, keyring_dir = signing_paths
        svc.import_trusted_collector("modecheck", _make_public_pem())
        path = os.path.join(keyring_dir, "modecheck.pub")
        assert os.stat(path).st_mode & 0o777 == 0o644
