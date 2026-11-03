# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Reading backup keys and the break-glass export in the open-source server
(2026-11-03): one implementation, the Pro+ engine calls it, and both work
with no license -- a lapse never locks anyone out of their own backups."""

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime

import pytest

from backend.persistence import models
from backend.services import backup_breakglass as bg
from backend.services import backup_keys_read as keys_read
from tests.services.test_backup_encryption import _encrypt
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)

SECRET = "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsec-%s\n"


class _Vault:
    def __init__(self, held):
        self.held, self.asked = held, []

    def retrieve_secret(self, reference):
        self.asked.append(reference)
        return {"content": self.held[reference]} if reference in self.held else {}


def _key_row(session, policy, ref, created, replaced=None):
    row = models.BackupPolicyKey(
        id=uuid.uuid4(), policy_id=policy.id, fingerprint=ref[-1] * 40,
        key_ref=ref, created_at=created, replaced_at=replaced,
    )  # fmt: skip
    session.add(row)
    session.commit()
    return row


def test_every_held_key_is_read_newest_first(session):
    s = _setup(session)
    _encrypt(session, s)
    s.policy.encrypt_key_ref = "ref/2"
    _key_row(session, s.policy, "ref/1", datetime(2026, 10, 1), datetime(2026, 11, 1))
    _key_row(session, s.policy, "ref/2", datetime(2026, 11, 1))
    vault = _Vault({"ref/1": SECRET % 1, "ref/2": SECRET % 2})
    assert keys_read.secret_keys(s.policy, db=session, vault=vault) == [
        SECRET % 2, SECRET % 1,
    ]  # fmt: skip


def test_a_missing_key_is_said_not_skipped(session):
    s = _setup(session)
    _encrypt(session, s)
    with pytest.raises(keys_read.BackupKeyReadError):
        keys_read.secret_keys(s.policy, db=session, vault=_Vault({}))
    s.policy.encrypt_key_ref = None
    with pytest.raises(keys_read.BackupKeyReadError):
        keys_read.secret_keys(s.policy, db=None, vault=_Vault({}))


def test_gather_reads_every_key_or_exports_nothing(session):
    s = _setup(session)
    _encrypt(session, s)
    _key_row(session, s.policy, "secret/data/secrets/backup_key/server/1",
             datetime(2026, 11, 1))  # fmt: skip
    (entry,) = bg.gather_export(
        session, [(s.host, s.policy)], s.target,
        vault=_Vault({"secret/data/secrets/backup_key/server/1": SECRET % 1}),
    )  # fmt: skip
    assert entry["host"] == s.host.fqdn and len(entry["keys"]) == 1
    with pytest.raises(bg.BreakGlassError):
        bg.gather_export(session, [(s.host, s.policy)], s.target, vault=_Vault({}))


def test_the_bundle_holds_the_readme_manifest_keys_and_signer():
    entries = [{"host": "web/01", "host_id": "h", "policy_id": "p", "repository": "r",
                "previous_repository": None, "storage_repository": "/srv/r",
                "keys": [{"fingerprint": "A" * 40, "subkey_id": None,
                          "created_at": None, "replaced_at": None,
                          "secret": SECRET % 1}]}]  # fmt: skip
    signer = {
        "fingerprint": "S" * 40,
        "public": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n",
    }
    raw = bg.build_bundle(
        entries, "2026-11-03T00:00:00Z", "admin", "drill", "F", signer
    )
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        names = archive.getnames()
        manifest = json.loads(archive.extractfile("manifest.json").read())
        readme = archive.extractfile("README.txt").read().decode()
    assert names[:2] == ["README.txt", "manifest.json"]
    assert "keys/web_01/1-" + "A" * 40 + ".asc" in names and bg.SIGNING_FILE in names
    assert "PRIVATE KEY" not in json.dumps(manifest)
    assert manifest["signing"]["file"] == bg.SIGNING_FILE
    assert "--trusted-key" in readme and "--decrypt-with" in readme


@pytest.mark.parametrize(
    "key,why",
    [("-----BEGIN PGP PRIVATE KEY BLOCK-----\n", "SECRET"), ("hello", "armored"),
     (None, "armored")],
)  # fmt: skip
def test_a_bad_recipient_is_refused(key, why):
    with pytest.raises(bg.BreakGlassRefused, match=why):
        bg.inspect_recipient(key)


def test_a_reason_must_say_something():
    with pytest.raises(bg.BreakGlassRefused):
        bg.check_reason("  short  ")
    assert bg.check_reason("  annual DR escrow  ") == "annual DR escrow"


def _msys_gpg() -> bool:
    """Git for Windows' MSYS gpg -- the first on PATH on the GitHub Windows
    runner.  Its gpg-agent does not start under --batch there, so key
    generation exits 2 (2026-11-03); a Windows server runs Gpg4win."""
    found = (shutil.which("gpg") or "").lower().replace("/", "\\")
    return sys.platform == "win32" and "\\git\\" in found


def _gpg_ok(argv, **kwargs):
    """Run gpg, failing with ITS message rather than a bare exit status."""
    done = subprocess.run(argv, capture_output=True, check=False, **kwargs)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return done


@pytest.mark.skipif(shutil.which("gpg") is None, reason="needs gpg")
@pytest.mark.skipif(
    _msys_gpg(), reason="Git for Windows' MSYS gpg cannot run its agent in CI"
)
def test_a_real_operator_key_seals_and_opens_the_export():
    root = tempfile.mkdtemp(prefix="bgo-", dir="/tmp")  # nosec B108
    try:
        home = tempfile.mkdtemp(prefix="op-", dir=root)
        base = ["gpg", "--homedir", home, "--batch", "--pinentry-mode", "loopback",
                "--passphrase", ""]  # fmt: skip
        _gpg_ok(
            base + ["--quick-gen-key", "Op <op@lab.invalid>", "rsa3072", "encr", "1d"]
        )
        public = _gpg_ok(
            base + ["--armor", "--export", "op@lab.invalid"]
        ).stdout.decode()
        fingerprint, uid = bg.inspect_recipient(public, tmp_root=root)
        assert len(fingerprint) == 40 and "op@lab.invalid" in uid
        sealed = bg.seal_bundle(b"bundle-bytes", public, fingerprint, tmp_root=root)
        opened = _gpg_ok(base + ["--decrypt"], input=sealed.encode()).stdout
        assert opened == b"bundle-bytes"
        subprocess.run(["gpgconf", "--homedir", home, "--kill", "all"], check=False)
    finally:
        shutil.rmtree(root, ignore_errors=True)
