# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Periodic orchestrator for ``AirgapIngestionRun`` lifecycle (repository side).

This is the repository-half mirror of ``airgap_run_tick`` (the
collector orchestrator).  The Pro+ ``airgap_repository_engine``'s
``POST /airgap/repository/ingest`` route inserts a row at
``status=QUEUED`` and walks away — historically nothing drove it
forward, so a freshly-transferred ISO sat at QUEUED forever (the exact
gap the collector had before its orchestrator was built).

This module is that worker.  Pattern mirrors ``airgap_run_tick``: a
30-second async loop, one tick per iteration, never lets a single
failure poison the loop.

Lifecycle the tick + result handler drive:

    QUEUED        → dispatch a mount plan (loop-mount the ISO read-only
                    + cat the embedded ``/manifest.json``) to the
                    repository host's agent.  Status → VERIFYING_SIG.
    VERIFYING_SIG → (no tick action; waiting on the mount agent result)
    VERIFIED      → dispatch a copy plan (rsync the mounted payload into
                    the local mirror tree + unmount).  Status → COPYING.
    COPYING       → (no tick action; waiting on the copy agent result)
    COMPLETE / FAILED → terminal.

The agent-result transitions live in
``proplus_dispatch._apply_airgap_ingest_result``, which calls
``process_mount_result`` / ``process_copy_result`` below:

  * mount result  → verify the embedded signed manifest against the
                    trusted-collector keyring (``verify_signed_envelope``
                    by signer fingerprint).  On success record the
                    provenance + set VERIFIED; on failure set FAILED.
                    Verification happens here (not in the tick) because
                    the mount outcome is where the manifest bytes land.
  * copy result   → set COMPLETE, capture rsync file/byte counts, and
                    register per-distro ``AirgapLocalRepository`` rows
                    from the verified manifest's ``targets``.

Trust model (v1): the signed manifest proves the media came from a
trusted collector (the only key on the repository's keyring is the one
embedded into the bundle at build time).  Per-package integrity is
provided by the mirror's own upstream-signed ``Release`` / ``repodata``
metadata, which apt/dnf verify at client ``update`` time — so we do not
re-hash every payload file here.  Per-file hash re-verification (using
the manifest's ``files`` list) and disc-aware multi-disc merge are
documented hardening follow-ups.

Single-box assumption: the mount/copy plans run on the Host registered
with this server's own hostname (``_find_repository_host``).  The
canonical repository deployment is a single air-gapped box that both
runs sysmanage and holds the transferred media.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import socket
from datetime import datetime, timezone

from backend.config import config as config_module
from backend.licensing.module_loader import module_loader
from backend.persistence.db import get_db
from backend.persistence import models

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 30
ERROR_BACKOFF_SECONDS = 30

# Lifecycle constants — single source of truth shared with the result
# handler so both agree on the legal status strings.
STATUS_QUEUED = "QUEUED"
STATUS_VERIFYING_SIG = "VERIFYING_SIG"
STATUS_VERIFIED = "VERIFIED"
STATUS_COPYING = "COPYING"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED = "FAILED"

# Where the ISO is loop-mounted and where the verified payload is
# rsynced.  Match the constants the engine's ``build_ingestion_plan``
# baked in so a repository configured by either path lines up.
MOUNT_POINT = "/mnt/sysmanage-airgap-ingest"
REPO_ROOT = "/var/lib/sysmanage/airgap-repo"

# rsync --stats parse (same two reliably-parseable lines the mirror
# snapshot path keys off; commas stripped before int()).
_RSYNC_FILES_RE = re.compile(r"Number of files:\s*([\d,]+)")
_RSYNC_BYTES_RE = re.compile(r"Total file size:\s*([\d,]+)\s+bytes")


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Host resolution
# ---------------------------------------------------------------------------
def _find_repository_host(db) -> "models.Host | None":
    """Return the Host row this repository's ingest plans dispatch to.

    Same FQDN-then-hostname match the collector orchestrator uses: the
    repository server is the box holding the media, so we dispatch to
    the Host registered with this server's own hostname.  Returns None
    when neither matches — the caller marks the run FAILED with a clear
    message rather than dispatching into the void.
    """
    fqdn = socket.getfqdn()
    bare = socket.gethostname()
    host = db.query(models.Host).filter(models.Host.fqdn == fqdn).first()
    if host is not None:
        return host
    return db.query(models.Host).filter(models.Host.fqdn == bare).first()


# ---------------------------------------------------------------------------
# Plan builders
# ---------------------------------------------------------------------------
def _cmd(argv, timeout, ignore_errors, description, desc_key):
    return {
        "argv": argv,
        "timeout": timeout,
        "ignore_errors": ignore_errors,
        "description": description,
        "description_key": desc_key,
        "description_params": {},
    }


def _is_block_device_path(iso_path: str) -> bool:
    """True when the ingest source is a block device node (optical /
    USB media) rather than an ISO *file*.  Device-based import (insert /
    burn the disc, pick the drive in the UI) passes ``/dev/sr0`` etc.;
    file-based import passes a path under the repo's incoming dir.
    """
    return bool(iso_path) and iso_path.startswith("/dev/")


def _build_mount_plan(iso_path: str) -> dict:
    """Mount the ingest media read-only and read its embedded manifest.

    Handles both sources:
      * an ISO *file*  → ``mount -o loop,ro`` (loop-back the file).
      * a block device → ``mount -o ro`` (mount the optical/USB node
        directly; a loop device would be wrong/refused for a real block
        device).

    A leading best-effort ``umount`` clears any stale mount left by a
    prior failed ingest (so the fresh ``mount`` to the same point never
    fails with "busy").  The final ``cat`` returns ``/manifest.json``'s
    bytes in the command result's stdout — that's what the mount result
    handler verifies against the keyring.  ``cat`` runs WITHOUT sudo:
    the manifest is world-readable, so no privileged read is needed (and
    none is granted in sudoers).
    """
    mount_opts = "ro" if _is_block_device_path(iso_path) else "loop,ro"
    return {
        "commands": [
            _cmd(
                ["sudo", "umount", MOUNT_POINT],
                60,
                True,
                "unmount any stale ingest media",
                "engine.airgap_repository.cmd.umount_iso",
            ),
            _cmd(
                ["sudo", "mkdir", "-p", MOUNT_POINT],
                60,
                False,
                "create ISO mount point",
                "engine.airgap_repository.cmd.create_mount_point",
            ),
            _cmd(
                ["sudo", "mount", "-o", mount_opts, iso_path, MOUNT_POINT],
                120,
                False,
                "mount ingest media read-only",
                "engine.airgap_repository.cmd.mount_iso",
            ),
            _cmd(
                ["cat", MOUNT_POINT + "/manifest.json"],
                60,
                False,
                "read embedded manifest",
                "engine.airgap_repository.cmd.read_manifest",
            ),
        ]
    }


def _build_copy_plan() -> dict:
    """rsync the verified payload into the local mirror tree, then unmount.

    ``--delete-after`` makes the local tree a faithful mirror of the
    media (stale packages removed).  ``--stats`` lets the copy-result
    handler record file/byte counts.  The trailing ``umount`` is
    ignore-errors so a transient busy-unmount doesn't fail an otherwise
    successful ingest (the next mount's leading umount cleans up).
    """
    return {
        "commands": [
            _cmd(
                ["sudo", "mkdir", "-p", REPO_ROOT],
                60,
                False,
                "ensure repo root exists",
                "engine.airgap_repository.cmd.ensure_repo_root",
            ),
            _cmd(
                [
                    "sudo",
                    "rsync",
                    "-a",
                    "--delete-after",
                    "--stats",
                    MOUNT_POINT + "/",
                    REPO_ROOT + "/",
                ],
                7200,
                False,
                "rsync verified payload to repo root",
                "engine.airgap_repository.cmd.rsync_payload",
            ),
            _cmd(
                ["sudo", "umount", MOUNT_POINT],
                60,
                True,
                "umount ingest ISO",
                "engine.airgap_repository.cmd.umount_iso",
            ),
        ]
    }


# ---------------------------------------------------------------------------
# Keyring + manifest verification (called from the mount result handler)
# ---------------------------------------------------------------------------
def load_trusted_keyring(keyring_dir: str) -> list:
    """Load every trusted-collector public key in ``keyring_dir``.

    Returns ``[(path, pem_str), ...]`` for files that look like PEM
    public keys (contain a ``PUBLIC KEY`` header).  Missing directory or
    unreadable files degrade to an empty/partial list rather than
    raising — the caller turns "no keys" into a clear ingest failure.
    """
    keys: list = []
    try:
        names = sorted(os.listdir(keyring_dir))
    except OSError:
        return keys
    for name in names:
        if not name.endswith((".pem", ".pub", ".key", ".crt")):
            continue
        path = os.path.join(keyring_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                pem = fh.read()
        except OSError:
            continue
        if "PUBLIC KEY" in pem:
            keys.append((path, pem))
    return keys


def _pem_fingerprint(pem: str) -> str:
    """sha256 over the *canonical* SubjectPublicKeyInfo PEM bytes.

    Re-serialises the key through cryptography so the hash is byte-for-
    byte what the collector's ``sign_manifest`` computed
    (``sha256(public_bytes(PEM, SubjectPublicKeyInfo))``), regardless of
    trailing-whitespace differences in how the keyring file was stored.
    Used only to *order* keys for the verify loop; the signature check
    is the source of truth, so a "" return (unparseable) just deprioritises.
    """
    try:
        from cryptography.hazmat.primitives import (  # pylint: disable=import-outside-toplevel
            serialization,
        )

        pub = serialization.load_pem_public_key(
            pem.encode("utf-8") if isinstance(pem, str) else pem
        )
        canon = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return hashlib.sha256(canon).hexdigest()
    except Exception:  # pylint: disable=broad-exception-caught
        return ""


def verify_envelope_against_keyring(engine, envelope, keyring_dir, strict) -> dict:
    """Verify a signed manifest envelope against the trusted keyring.

    Tries the fingerprint-matched key first (cheap optimisation), then
    falls back to every other key — the signature verification in
    ``engine.verify_signed_envelope`` is the real gate.  Returns the
    inner manifest dict on success.

    Raises the engine's ``MediaVerificationError`` when no trusted key
    validates the signature (or the keyring is empty), and re-raises
    ``StaleManifestError`` immediately (a too-new format is terminal —
    no other key would help; the operator must upgrade the repository).
    """
    mv_err = getattr(engine, "MediaVerificationError", ValueError)
    stale_err = getattr(engine, "StaleManifestError", None)

    keys = load_trusted_keyring(keyring_dir)
    if not keys:
        raise mv_err(
            f"no trusted collector public keys found in keyring '{keyring_dir}'; "
            "embed the collector's public key on the repository before ingesting media"
        )

    fp = envelope.get("signer_fingerprint") if isinstance(envelope, dict) else None
    ordered = sorted(
        keys, key=lambda kp: 0 if fp and _pem_fingerprint(kp[1]) == fp else 1
    )

    last_err = None
    for _path, pem in ordered:
        try:
            return engine.verify_signed_envelope(envelope, pem, strict)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if stale_err is not None and isinstance(exc, stale_err):
                raise
            last_err = exc
            continue
    raise mv_err(
        "no trusted collector key verified the manifest signature "
        f"(tried {len(ordered)} key(s)): {last_err}"
    )


def _manifest_from_mount_outcome(outcome: dict):
    """Pull the embedded manifest envelope out of the mount plan result.

    Finds the ``cat .../manifest.json`` command in the per-command
    results and JSON-parses its stdout.  Returns the parsed envelope
    dict, or None when the command/stdout is missing or unparseable
    (caller turns that into a clear "is this a sysmanage air-gap ISO?"
    failure).
    """
    for cmd in outcome.get("commands") or []:
        argv = cmd.get("argv") or []
        if argv and str(argv[-1]).endswith("/manifest.json"):
            raw = (cmd.get("stdout") or "").strip()
            if not raw:
                return None
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                return None
    return None


def _parse_rsync_int(stdout, pattern):
    """First capture group of ``pattern`` in ``stdout`` as an int, or None."""
    match = pattern.search(stdout)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _ingest_rsync_stats(outcome: dict) -> dict:
    """Parse file/byte counts from the copy plan's rsync ``--stats``."""
    result = {"files": None, "bytes": None}
    for cmd in outcome.get("commands") or []:
        argv = cmd.get("argv") or []
        if "rsync" not in " ".join(str(a) for a in argv):
            continue
        stdout = cmd.get("stdout") or ""
        files = _parse_rsync_int(stdout, _RSYNC_FILES_RE)
        if files is not None:
            result["files"] = files
        size = _parse_rsync_int(stdout, _RSYNC_BYTES_RE)
        if size is not None:
            result["bytes"] = size
    return result


# ---------------------------------------------------------------------------
# Result-side processors (invoked by proplus_dispatch with an open session)
# ---------------------------------------------------------------------------
def process_mount_result(_session, run, outcome) -> None:
    """Verify the mounted media's manifest; set VERIFIED or FAILED.

    Caller has already confirmed the mount plan *succeeded* and cleared
    ``worker_message_id``; this only handles the verify decision.  The
    caller commits.
    """
    engine = module_loader.get_module("airgap_repository_engine")
    if engine is None:
        _fail(run, "airgap_repository_engine not loaded; cannot verify ingest media")
        return

    envelope = _manifest_from_mount_outcome(outcome)
    if envelope is None:
        _fail(
            run,
            "could not read /manifest.json from the mounted media — is this a "
            "sysmanage air-gap ISO?",
        )
        return

    keyring_dir = config_module.get_airgap_collector_public_key_dir()
    strict = config_module.is_airgap_verify_strict()
    try:
        manifest = verify_envelope_against_keyring(
            engine, envelope, keyring_dir, strict
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _fail(run, f"manifest verification failed: {exc}")
        return

    run.signer_fingerprint = (
        envelope.get("signer_fingerprint") if isinstance(envelope, dict) else None
    )
    run.manifest_format_version = manifest.get("format_version") or (
        envelope.get("format_version") if isinstance(envelope, dict) else None
    )
    run.collector_iso_label = manifest.get("iso_label")
    run.manifest_json = json.dumps(manifest, separators=(",", ":"))
    run.status = STATUS_VERIFIED
    run.error_message = None


def process_copy_result(session, run, outcome) -> None:
    """Finalize a successful copy: COMPLETE + counts + repo registration."""
    stats = _ingest_rsync_stats(outcome)
    if stats.get("files") is not None:
        run.file_count = stats["files"]
    if stats.get("bytes") is not None:
        run.byte_count = stats["bytes"]
    run.status = STATUS_COMPLETE
    run.completed_at = _now_naive()
    run.error_message = None
    _register_local_repositories(session, run)


def _mirror_base_url() -> str:
    """Base URL air-gapped agents use to reach this repository's mirror.

    Host is this server's own name (single-box air-gap deploy serves the
    mirror from the same host that runs sysmanage); port is the webui
    nginx port that serves ``/airgap-repo/`` (omitted when it's 80).
    NOT ``localhost`` — other air-gapped agents have to resolve it.
    """
    host = socket.getfqdn() or socket.gethostname()
    port = 0
    try:
        webui = config_module.get_config().get("webui", {}) or {}
        port = int(webui.get("port") or 0)
    except (ValueError, TypeError, AttributeError):
        port = 0
    netloc = host if port in (0, 80) else f"{host}:{port}"
    return f"http://{netloc}/airgap-repo"  # NOSONAR S5332 - air-gap LAN repo, no PKI in the enclave; agents fetch over http intentionally


def _discover_apt_root(distro: str, version: str):
    """Locate the real apt repo root for a copied target and count debs.

    The collector mirrors with ``apt-mirror``, whose on-disk layout
    nests the serveable tree under ``mirror/<upstream-host>/<path>`` (a
    metadata-only ``skel/`` sits alongside it).  Rather than assume a
    flat tree, find the directory that holds BOTH ``dists/`` and
    ``pool/`` — that's the apt root.  Returns
    ``(relpath_from_REPO_ROOT, deb_count)`` or ``(None, None)`` when the
    tree isn't found (best-effort; caller falls back).
    """
    base = os.path.join(REPO_ROOT, distro, version)
    if not os.path.isdir(base):
        return None, None
    apt_root = None
    for root, dirs, _files in os.walk(base):
        if "dists" in dirs and "pool" in dirs:
            apt_root = root
            break
    if apt_root is None:
        return None, None
    rel = os.path.relpath(apt_root, REPO_ROOT)
    count = 0
    for _root, _dirs, files in os.walk(os.path.join(apt_root, "pool")):
        count += sum(1 for f in files if f.endswith(".deb"))
    return rel, count


def _register_local_repositories(session, run) -> None:
    """Upsert one ``AirgapLocalRepository`` per verified manifest target.

    Drives the repository UI's repo list + compliance staleness.  Keyed
    on (distro, version); re-ingest of the same distro just refreshes
    ``last_ingest_*``.  Best-effort: a malformed/absent manifest skips
    registration without failing the ingest (freshness still works off
    ``AirgapIngestionRun.completed_at``).
    """
    if not run.manifest_json:
        return
    try:
        manifest = json.loads(run.manifest_json)
    except (ValueError, TypeError):
        return
    targets = manifest.get("targets") or []
    now = _now_naive()
    base_url = _mirror_base_url()
    for target in targets:
        if not isinstance(target, dict):
            continue
        distro = target.get("distro")
        version = target.get("version")
        if not distro or not version:
            continue
        rel, pkg_count = _discover_apt_root(distro, version)
        repo_url = f"{base_url}/{rel}" if rel else f"{base_url}/{distro}/{version}"
        row = (
            session.query(models.AirgapLocalRepository)
            .filter(
                models.AirgapLocalRepository.distro == distro,
                models.AirgapLocalRepository.version == version,
            )
            .first()
        )
        if row is None:
            row = models.AirgapLocalRepository(
                distro=distro,
                version=version,
                repo_url=repo_url,
            )
            session.add(row)
        else:
            row.repo_url = repo_url
        row.last_ingest_run_id = run.id
        row.last_ingest_at = now
        row.package_count = pkg_count


# ---------------------------------------------------------------------------
# Tick-side advancement
# ---------------------------------------------------------------------------
def _fail(run, reason: str) -> None:
    """Mark a run FAILED with a captured reason; clear in-flight marker."""
    if run.status == STATUS_FAILED:
        return
    run.status = STATUS_FAILED
    run.error_message = reason[:8000]
    run.worker_message_id = None
    run.completed_at = _now_naive()


def _advance_queued(db, run) -> None:
    """QUEUED → dispatch the mount/read-manifest plan → VERIFYING_SIG."""
    if not run.iso_path:
        _fail(run, "ingestion run has no iso_path to mount")
        return
    host = _find_repository_host(db)
    if host is None:
        _fail(
            run,
            "no registered Host matches this repository server's hostname; the "
            "repository box must run a sysmanage agent registered to this server",
        )
        return
    plan = _build_mount_plan(run.iso_path)
    try:
        from backend.services.proplus_dispatch import (  # pylint: disable=import-outside-toplevel
            enqueue_apply_plan,
            register_airgap_ingest_correlation,
        )

        msg_id = enqueue_apply_plan(host_id=str(host.id), plan=plan, timeout=300)
        register_airgap_ingest_correlation(msg_id, "mount", str(run.id), str(host.id))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _fail(run, f"mount plan dispatch failed: {exc}")
        return
    run.status = STATUS_VERIFYING_SIG
    run.started_at = _now_naive()
    run.worker_message_id = msg_id
    run.error_message = None


def _advance_verified(db, run) -> None:
    """VERIFIED → dispatch the rsync copy plan → COPYING."""
    host = _find_repository_host(db)
    if host is None:
        _fail(run, "repository host no longer registered between mount and copy")
        return
    plan = _build_copy_plan()
    try:
        from backend.services.proplus_dispatch import (  # pylint: disable=import-outside-toplevel
            enqueue_apply_plan,
            register_airgap_ingest_correlation,
        )

        msg_id = enqueue_apply_plan(host_id=str(host.id), plan=plan, timeout=7200)
        register_airgap_ingest_correlation(msg_id, "copy", str(run.id), str(host.id))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _fail(run, f"copy plan dispatch failed: {exc}")
        return
    run.status = STATUS_COPYING
    run.worker_message_id = msg_id
    run.error_message = None


def _run_one_tick() -> dict:
    """Advance every AirgapIngestionRun that's ready to progress."""
    summary = {"advanced": 0, "failed": 0, "skipped_inflight": 0}
    if module_loader.get_module("airgap_repository_engine") is None:
        return summary

    db = next(get_db())
    try:
        rows = (
            db.query(models.AirgapIngestionRun)
            .filter(
                models.AirgapIngestionRun.status.in_([STATUS_QUEUED, STATUS_VERIFIED])
            )
            .all()
        )
        for run in rows:
            # Defense-in-depth: a ready-to-advance row should never still
            # carry an in-flight marker, but if a result handler crashed
            # mid-update, don't re-dispatch on top of a running plan.
            if run.worker_message_id is not None:
                summary["skipped_inflight"] += 1
                continue
            try:
                if run.status == STATUS_QUEUED:
                    _advance_queued(db, run)
                elif run.status == STATUS_VERIFIED:
                    _advance_verified(db, run)
                if run.status == STATUS_FAILED:
                    summary["failed"] += 1
                else:
                    summary["advanced"] += 1
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "airgap ingest tick failed for run %s: %s", run.id, exc
                )
                _fail(run, f"tick exception: {exc}")
                summary["failed"] += 1
        if rows:
            db.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("airgap ingest tick batch failed")
        db.rollback()
    finally:
        db.close()
    return summary


async def airgap_ingest_tick_service() -> None:
    """Background service: advance every ingestion run every tick.

    Started from ``backend/startup/lifecycle.py`` only when the
    ``airgap_repository_engine`` Pro+ module is loaded — same gating
    convention as the collector's run tick.
    """
    logger.info(
        "Starting air-gap ingestion tick service (interval=%ds)",
        TICK_INTERVAL_SECONDS,
    )
    while True:
        try:
            summary = _run_one_tick()
            if summary["advanced"] or summary["failed"]:
                logger.info(
                    "Air-gap ingest tick: advanced=%d failed=%d skipped_inflight=%d",
                    summary["advanced"],
                    summary["failed"],
                    summary["skipped_inflight"],
                )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Air-gap ingest tick service cancelled")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("airgap ingest tick service outer loop error")
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)
