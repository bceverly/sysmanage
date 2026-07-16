# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the repository-side air-gap ingestion orchestrator."""

# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access

import base64
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.persistence import models
from backend.services import airgap_ingest_tick as tick


# ---------------------------------------------------------------------------
# Crypto helpers — faithful to the collector's sign_manifest + the
# repository engine's verify_signed_envelope so the keyring logic is
# exercised against real ed25519 signatures, not a mock.
# ---------------------------------------------------------------------------
def _pub_pem(private_key) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _make_signed_envelope(manifest: dict, private_key, fmt: int = 1) -> dict:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    sig = private_key.sign(payload)
    digest = hashes.Hash(hashes.SHA256())
    digest.update(_pub_pem(private_key))
    return {
        "manifest": manifest,
        "signature": base64.b64encode(sig).decode("ascii"),
        "signer_fingerprint": digest.finalize().hex(),
        "signature_algorithm": "ed25519",
        "format_version": fmt,
    }


class _StubRepoEngine:
    """Minimal stand-in for airgap_repository_engine with a real verify."""

    class MediaVerificationError(ValueError):
        pass

    class StaleManifestError(ValueError):
        pass

    MAX_SUPPORTED_FORMAT_VERSION = 1

    def verify_signed_envelope(self, envelope, public_key_pem, strict=True):
        from cryptography.exceptions import InvalidSignature

        manifest = envelope.get("manifest")
        fmt = manifest.get("format_version", envelope.get("format_version", 0))
        if fmt > self.MAX_SUPPORTED_FORMAT_VERSION:
            raise self.StaleManifestError("manifest too new")
        algo = envelope.get("signature_algorithm")
        if algo == "hmac-sha256-fallback" and strict:
            raise self.MediaVerificationError("strict rejects hmac fallback")
        if algo != "ed25519":
            raise self.MediaVerificationError(f"bad algo {algo!r}")
        if not public_key_pem:
            raise self.MediaVerificationError("missing pubkey")
        pub = serialization.load_pem_public_key(
            public_key_pem.encode()
            if isinstance(public_key_pem, str)
            else public_key_pem
        )
        payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        try:
            pub.verify(base64.b64decode(envelope["signature"]), payload)
        except InvalidSignature as exc:
            raise self.MediaVerificationError("signature mismatch") from exc
        return manifest


def _write_keyring(tmp_path, *private_keys):
    keyring = tmp_path / "trusted-collectors"
    keyring.mkdir()
    for idx, pk in enumerate(private_keys):
        (keyring / f"key{idx}.pub").write_bytes(_pub_pem(pk))
    # A non-key file that must be ignored.
    (keyring / "README.txt").write_text("not a key")
    return str(keyring)


def _mount_outcome(envelope, *, status="succeeded"):
    """Shape a mount-plan outcome with the manifest in the cat command."""
    return {
        "status": status,
        "commands": [
            {"argv": ["sudo", "umount", tick.MOUNT_POINT], "success": True},
            {"argv": ["sudo", "mkdir", "-p", tick.MOUNT_POINT], "success": True},
            {
                "argv": ["sudo", "mount", "-o", "loop,ro", "/x.iso", tick.MOUNT_POINT],
                "success": True,
            },
            {
                "argv": ["cat", tick.MOUNT_POINT + "/manifest.json"],
                "success": True,
                "stdout": json.dumps(envelope),
            },
        ],
    }


# ---------------------------------------------------------------------------
# Plan builders
# ---------------------------------------------------------------------------
def test_mount_plan_mounts_ro_and_reads_manifest():
    plan = tick._build_mount_plan("/media/run.iso")
    argvs = [c["argv"] for c in plan["commands"]]
    # Read-only loop mount of the supplied iso.
    assert [
        "sudo",
        "mount",
        "-o",
        "loop,ro",
        "/media/run.iso",
        tick.MOUNT_POINT,
    ] in argvs
    # Leading umount is best-effort so a stale mount never blocks.
    assert argvs[0] == ["sudo", "umount", tick.MOUNT_POINT]
    assert plan["commands"][0]["ignore_errors"] is True
    # Final step cats the embedded manifest WITHOUT sudo.
    assert argvs[-1] == ["cat", tick.MOUNT_POINT + "/manifest.json"]
    assert argvs[-1][0] == "cat"


def test_copy_plan_rsyncs_then_unmounts():
    plan = tick._build_copy_plan()
    argvs = [c["argv"] for c in plan["commands"]]
    assert any(a[:2] == ["sudo", "rsync"] and "--stats" in a for a in argvs)
    assert any(a[:2] == ["sudo", "rsync"] and "--delete-after" in a for a in argvs)
    assert argvs[-1] == ["sudo", "umount", tick.MOUNT_POINT]
    assert plan["commands"][-1]["ignore_errors"] is True


# ---------------------------------------------------------------------------
# Keyring + fingerprint + manifest extraction
# ---------------------------------------------------------------------------
def test_load_trusted_keyring_only_returns_public_keys(tmp_path):
    pk = Ed25519PrivateKey.generate()
    keyring_dir = _write_keyring(tmp_path, pk)
    keys = tick.load_trusted_keyring(keyring_dir)
    assert len(keys) == 1
    assert "PUBLIC KEY" in keys[0][1]


def test_load_trusted_keyring_missing_dir_is_empty():
    assert tick.load_trusted_keyring("/no/such/dir") == []


def test_pem_fingerprint_matches_collector_computation():
    pk = Ed25519PrivateKey.generate()
    pub_pem = _pub_pem(pk)
    digest = hashes.Hash(hashes.SHA256())
    digest.update(pub_pem)
    expected = digest.finalize().hex()
    assert tick._pem_fingerprint(pub_pem.decode()) == expected


def test_manifest_extraction_from_outcome():
    pk = Ed25519PrivateKey.generate()
    env = _make_signed_envelope({"format_version": 1, "iso_label": "x"}, pk)
    assert tick._manifest_from_mount_outcome(_mount_outcome(env)) == env


def test_manifest_extraction_handles_garbage():
    outcome = {
        "commands": [
            {"argv": ["cat", tick.MOUNT_POINT + "/manifest.json"], "stdout": "}{bad"}
        ]
    }
    assert tick._manifest_from_mount_outcome(outcome) is None


def test_manifest_extraction_handles_missing_command():
    assert tick._manifest_from_mount_outcome({"commands": []}) is None


# ---------------------------------------------------------------------------
# verify_envelope_against_keyring — the security gate
# ---------------------------------------------------------------------------
def test_verify_accepts_trusted_key(tmp_path):
    pk = Ed25519PrivateKey.generate()
    keyring_dir = _write_keyring(tmp_path, pk)
    env = _make_signed_envelope({"format_version": 1, "iso_label": "ok"}, pk)
    manifest = tick.verify_envelope_against_keyring(
        _StubRepoEngine(), env, keyring_dir, strict=True
    )
    assert manifest["iso_label"] == "ok"


def test_verify_rejects_untrusted_key(tmp_path):
    trusted = Ed25519PrivateKey.generate()
    attacker = Ed25519PrivateKey.generate()
    keyring_dir = _write_keyring(tmp_path, trusted)
    env = _make_signed_envelope({"format_version": 1}, attacker)
    with pytest.raises(_StubRepoEngine.MediaVerificationError):
        tick.verify_envelope_against_keyring(
            _StubRepoEngine(), env, keyring_dir, strict=True
        )


def test_verify_empty_keyring_fails_clearly(tmp_path):
    pk = Ed25519PrivateKey.generate()
    env = _make_signed_envelope({"format_version": 1}, pk)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(_StubRepoEngine.MediaVerificationError, match="no trusted"):
        tick.verify_envelope_against_keyring(
            _StubRepoEngine(), env, str(empty), strict=True
        )


def test_verify_stale_format_is_terminal(tmp_path):
    pk = Ed25519PrivateKey.generate()
    keyring_dir = _write_keyring(tmp_path, pk)
    env = _make_signed_envelope({"format_version": 99}, pk, fmt=99)
    with pytest.raises(_StubRepoEngine.StaleManifestError):
        tick.verify_envelope_against_keyring(
            _StubRepoEngine(), env, keyring_dir, strict=True
        )


def test_verify_picks_correct_key_among_many(tmp_path):
    others = [Ed25519PrivateKey.generate() for _ in range(3)]
    signer = Ed25519PrivateKey.generate()
    keyring_dir = _write_keyring(tmp_path, *others, signer)
    env = _make_signed_envelope({"format_version": 1, "iso_label": "multi"}, signer)
    manifest = tick.verify_envelope_against_keyring(
        _StubRepoEngine(), env, keyring_dir, strict=True
    )
    assert manifest["iso_label"] == "multi"


# ---------------------------------------------------------------------------
# rsync stats
# ---------------------------------------------------------------------------
def test_ingest_rsync_stats_parses_counts():
    outcome = {
        "commands": [
            {"argv": ["sudo", "mkdir", "-p", "/x"]},
            {
                "argv": ["sudo", "rsync", "-a", "--stats", "/a/", "/b/"],
                "stdout": "Number of files: 1,234\nTotal file size: 5,678,900 bytes\n",
            },
        ]
    }
    stats = tick._ingest_rsync_stats(outcome)
    assert stats == {"files": 1234, "bytes": 5678900}


# ---------------------------------------------------------------------------
# Result processors (real DB session)
# ---------------------------------------------------------------------------
def _seed_ingestion_run(db_session, **kw):
    run = models.AirgapIngestionRun(
        iso_path=kw.get("iso_path", "/media/run.iso"), status=kw.get("status", "QUEUED")
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_process_mount_result_records_provenance_and_verifies(db_session, tmp_path):
    pk = Ed25519PrivateKey.generate()
    keyring_dir = _write_keyring(tmp_path, pk)
    env = _make_signed_envelope(
        {
            "format_version": 1,
            "iso_label": "rel-2026",
            "targets": [{"distro": "ubuntu", "version": "24.04"}],
        },
        pk,
    )
    run = _seed_ingestion_run(db_session, status="VERIFYING_SIG")

    with patch.object(
        tick.module_loader, "get_module", return_value=_StubRepoEngine()
    ), patch.object(
        tick.config_module,
        "get_airgap_collector_public_key_dir",
        return_value=keyring_dir,
    ), patch.object(
        tick.config_module, "is_airgap_verify_strict", return_value=True
    ):
        tick.process_mount_result(db_session, run, _mount_outcome(env))
        db_session.commit()

    assert run.status == tick.STATUS_VERIFIED
    assert run.signer_fingerprint == env["signer_fingerprint"]
    assert run.collector_iso_label == "rel-2026"
    assert json.loads(run.manifest_json)["targets"][0]["distro"] == "ubuntu"


def test_process_mount_result_untrusted_media_fails(db_session, tmp_path):
    trusted = Ed25519PrivateKey.generate()
    attacker = Ed25519PrivateKey.generate()
    keyring_dir = _write_keyring(tmp_path, trusted)
    env = _make_signed_envelope({"format_version": 1}, attacker)
    run = _seed_ingestion_run(db_session, status="VERIFYING_SIG")

    with patch.object(
        tick.module_loader, "get_module", return_value=_StubRepoEngine()
    ), patch.object(
        tick.config_module,
        "get_airgap_collector_public_key_dir",
        return_value=keyring_dir,
    ), patch.object(
        tick.config_module, "is_airgap_verify_strict", return_value=True
    ):
        tick.process_mount_result(db_session, run, _mount_outcome(env))
        db_session.commit()

    assert run.status == tick.STATUS_FAILED
    assert "verification failed" in run.error_message


def test_process_mount_result_unreadable_manifest_fails(db_session, tmp_path):
    keyring_dir = _write_keyring(tmp_path, Ed25519PrivateKey.generate())
    run = _seed_ingestion_run(db_session, status="VERIFYING_SIG")
    outcome = {
        "status": "succeeded",
        "commands": [
            {"argv": ["cat", tick.MOUNT_POINT + "/manifest.json"], "stdout": ""}
        ],
    }

    with patch.object(
        tick.module_loader, "get_module", return_value=_StubRepoEngine()
    ), patch.object(
        tick.config_module,
        "get_airgap_collector_public_key_dir",
        return_value=keyring_dir,
    ), patch.object(
        tick.config_module, "is_airgap_verify_strict", return_value=True
    ):
        tick.process_mount_result(db_session, run, outcome)
        db_session.commit()

    assert run.status == tick.STATUS_FAILED
    assert "manifest.json" in run.error_message


def test_process_copy_result_completes_and_registers_repos(db_session):
    run = _seed_ingestion_run(db_session, status="COPYING")
    run.manifest_json = json.dumps(
        {
            "targets": [
                {"distro": "ubuntu", "version": "24.04"},
                {"distro": "debian", "version": "12"},
            ]
        }
    )
    db_session.commit()
    outcome = {
        "status": "succeeded",
        "commands": [
            {
                "argv": ["sudo", "rsync", "-a", "--stats", "/a/", "/b/"],
                "stdout": "Number of files: 10\nTotal file size: 2,000 bytes\n",
            }
        ],
    }

    tick.process_copy_result(db_session, run, outcome)
    db_session.commit()

    assert run.status == tick.STATUS_COMPLETE
    assert run.completed_at is not None
    assert run.file_count == 10
    assert run.byte_count == 2000
    repos = db_session.query(models.AirgapLocalRepository).all()
    assert {(r.distro, r.version) for r in repos} == {
        ("ubuntu", "24.04"),
        ("debian", "12"),
    }
    assert all(r.last_ingest_run_id == run.id for r in repos)


# ---------------------------------------------------------------------------
# Tick advancement
# ---------------------------------------------------------------------------
def _seed_host(db_session, fqdn):
    host = models.Host(fqdn=fqdn, active=True)
    db_session.add(host)
    db_session.commit()
    db_session.refresh(host)
    return host


def test_advance_queued_dispatches_mount_and_sets_verifying(db_session):
    host = _seed_host(db_session, "repo.example.test")
    run = _seed_ingestion_run(db_session, status="QUEUED")

    with patch.object(tick.socket, "getfqdn", return_value="repo.example.test"), patch(
        "backend.services.proplus_dispatch.enqueue_apply_plan", return_value="msg-1"
    ) as enq, patch(
        "backend.services.proplus_dispatch.register_airgap_ingest_correlation"
    ) as reg:
        tick._advance_queued(db_session, run)

    assert run.status == tick.STATUS_VERIFYING_SIG
    assert run.worker_message_id == "msg-1"
    enq.assert_called_once()
    # Correlation tagged with the "mount" stage + this run id.
    args = reg.call_args[0]
    assert args[1] == "mount" and args[2] == str(run.id)


def test_advance_queued_without_host_fails(db_session):
    run = _seed_ingestion_run(db_session, status="QUEUED")
    with patch.object(tick.socket, "getfqdn", return_value="nobody.here"), patch.object(
        tick.socket, "gethostname", return_value="nobody.here"
    ):
        tick._advance_queued(db_session, run)
    assert run.status == tick.STATUS_FAILED
    assert "no registered Host" in run.error_message


def test_advance_verified_dispatches_copy(db_session):
    _seed_host(db_session, "repo.example.test")
    run = _seed_ingestion_run(db_session, status="VERIFIED")

    with patch.object(tick.socket, "getfqdn", return_value="repo.example.test"), patch(
        "backend.services.proplus_dispatch.enqueue_apply_plan", return_value="msg-2"
    ), patch(
        "backend.services.proplus_dispatch.register_airgap_ingest_correlation"
    ) as reg:
        tick._advance_verified(db_session, run)

    assert run.status == tick.STATUS_COPYING
    assert run.worker_message_id == "msg-2"
    assert reg.call_args[0][1] == "copy"


def test_run_one_tick_no_engine_is_noop():
    with patch.object(tick.module_loader, "get_module", return_value=None):
        summary = tick._run_one_tick()
    assert summary == {"advanced": 0, "failed": 0, "skipped_inflight": 0}


def test_run_one_tick_skips_inflight(db_session):
    from sqlalchemy.orm import Session

    run = _seed_ingestion_run(db_session, status="QUEUED")
    run.worker_message_id = "still-running"
    db_session.commit()
    run_id = run.id
    engine = db_session.get_bind()

    # _run_one_tick opens its own session via get_db() and closes it in a
    # finally — hand it a *separate* session so the fixture session stays
    # usable for the re-read assertion below.
    def _fake_get_db():
        yield Session(bind=engine)

    with patch.object(
        tick.module_loader, "get_module", return_value=_StubRepoEngine()
    ), patch.object(tick, "get_db", _fake_get_db):
        summary = tick._run_one_tick()
    assert summary["skipped_inflight"] == 1
    db_session.expire_all()
    reread = db_session.query(models.AirgapIngestionRun).filter_by(id=run_id).first()
    assert reread.status == "QUEUED"
