# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Periodic orchestrator for ``AirgapCollectionRun`` lifecycle.

The schedule-tick service (``airgap_schedule_tick.py``) and the
``POST /collection/runs`` endpoint both insert run rows at
``status=QUEUED`` and then walk away — historically there was no
in-process worker to take a QUEUED row through MIRRORING /
STAGING_COMPLETE / BUILDING_ISO / ISO_BUILT.  An operator who clicked
"New collection run" got a row that sat at QUEUED forever; the
docstring in ``backend/api/airgap_collector_runs.py`` describing a
"background worker that picks the row up" was aspirational.

This module is that worker.  Pattern mirrors ``airgap_schedule_tick``:
a 30-second async loop that does one tick per iteration and never lets
a single failure poison the loop.

Option-B sourcing: the collection plan rsyncs from each target's
mirror snapshot dir (``<mirror_root>/<name>/.snapshots/<id>/``) into
the staging tree.  No upstream apt-mirror / reposync runs at
collection time — the source-of-truth fetch happened earlier inside
``repository_mirroring_engine`` when the operator synced their LAN
mirrors.

Lifecycle the tick drives:

    QUEUED           → if any target's snapshot is still in flight,
                       leave QUEUED.  Else: build the snapshot-sourced
                       collection plan, dispatch to the target host,
                       set MIRRORING.  If any snapshot FAILED → set
                       run to FAILED.
    MIRRORING        → (no action; waiting on agent result)
    STAGING_COMPLETE → build ISO plan, dispatch, set BUILDING_ISO
    BUILDING_ISO     → (no action; waiting on agent result)
    ISO_BUILT        → if ``burn_device`` set: build burn plan,
                       dispatch, set BURNING.  Else: set COMPLETE.
    BURNING          → (no action; waiting on agent result)

The agent-side transitions (MIRRORING → STAGING_COMPLETE,
BUILDING_ISO → ISO_BUILT, BURNING → COMPLETE) are driven from
``proplus_dispatch._apply_airgap_run_result`` when the agent's
``command_result`` lands.

Failure handling: any plan-build or dispatch exception flips the row
to FAILED with ``error_message`` populated, and the tick continues to
the next row.  Operators see the FAILED chip in the UI and can read
the error via the same tooltip pattern used for mirror failures.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from datetime import datetime, timezone

from backend.licensing.module_loader import module_loader
from backend.persistence.db import get_db
from backend.persistence import models

logger = logging.getLogger(__name__)

# 30s — half the schedule-tick cadence.  Collection plans take minutes
# to hours, so a finer tick gains nothing; a coarser one would make
# the QUEUED→MIRRORING transition feel laggy in the UI.
TICK_INTERVAL_SECONDS = 30
ERROR_BACKOFF_SECONDS = 30


# Lifecycle constants — single source of truth so the tick + result
# handler agree on which strings are legal.
STATUS_QUEUED = "QUEUED"
STATUS_MIRRORING = "MIRRORING"
STATUS_STAGING_COMPLETE = "STAGING_COMPLETE"
STATUS_BUILDING_ISO = "BUILDING_ISO"
STATUS_ISO_BUILT = "ISO_BUILT"
STATUS_BURNING = "BURNING"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED = "FAILED"


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _manifest_targets(run: "models.AirgapCollectionRun") -> list:
    """The ``targets`` list embedded in (and signed with) the manifest.

    The repository side reads this off the verified ``/manifest.json``
    to populate its per-distro ``AirgapLocalRepository`` rows (which
    drive freshness + compliance staleness) without having to re-scan
    the copied tree.  Each entry is ``{distro, version}`` — the minimum
    the repository needs to register what it just ingested.  Embedded
    inside the signed payload so a tampered target list is rejected.
    """
    return [{"distro": t.distro, "version": t.version} for t in (run.targets or [])]


def _sign_manifest_or_raw(engine, manifest: dict) -> dict:
    """Return a signed manifest envelope, or the bare manifest on miss.

    Reads the collector's ed25519 private key and asks the engine's
    ``sign_manifest`` to wrap the manifest.  If the key is missing or
    the engine doesn't expose ``sign_manifest`` (older module), logs a
    warning and returns the unsigned manifest — the ISO still builds
    and downloads, it just won't pass a strict repository ingest.  That
    degrade-don't-crash choice keeps a key-misconfigured collector from
    failing the whole run; the operator sees unsigned bundles get
    rejected on ingest and fixes the key, rather than debugging a
    mid-run failure.
    """
    signer = getattr(engine, "sign_manifest", None)
    if signer is None:
        logger.warning(
            "collector engine has no sign_manifest; embedding UNSIGNED manifest"
        )
        return manifest
    try:
        from backend.services.airgap_signing_service import (  # pylint: disable=import-outside-toplevel
            get_collector_private_key_pem,
        )

        private_pem = get_collector_private_key_pem()
        if not private_pem:
            logger.warning(
                "collector signing key missing (set role to collector to "
                "generate it); embedding UNSIGNED manifest"
            )
            return manifest
        return signer(manifest, private_pem)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "manifest signing failed; embedding UNSIGNED manifest", exc_info=True
        )
        return manifest


def _find_collector_host(db) -> "models.Host | None":
    """Return the Host row this server's collection plans should dispatch to.

    The Pro+ engine's docstring describes collection plans as running
    on the collector itself, so we look up the Host row registered
    with the same FQDN as this server.  Falls back to the bare
    hostname if no FQDN match exists.  Returns None when neither
    matches — the caller logs and marks the run FAILED.

    Defending against the ambiguous case (multiple hosts registered
    with the same hostname): if the lookup is non-unique we still
    return the first row; a deduplication pass would belong in the
    Host model layer, not here.
    """
    fqdn = socket.getfqdn()
    bare = socket.gethostname()
    host = db.query(models.Host).filter(models.Host.fqdn == fqdn).first()
    if host is not None:
        return host
    return db.query(models.Host).filter(models.Host.fqdn == bare).first()


def _build_collection_request(run: models.AirgapCollectionRun) -> dict:
    """Translate the run row + its targets into the dict shape that
    ``airgap_collector_engine.build_snapshot_collection_run_plan``
    expects.

    Same envelope as the legacy ``build_collection_run_plan`` accepted
    (distros / include_cve / include_compliance / iso_label /
    media_size_bytes) plus a ``source_snapshots`` map keyed by
    ``"<distro>:<version>"`` whose value is the on-host path of the
    snapshot directory the plan must rsync from.

    Caller is responsible for catching the case where ``distros`` is
    empty.
    """
    distros = []
    for target in run.targets or []:
        repos = (target.repos or "").split(",") if target.repos else []
        distros.append(
            {
                "distro": target.distro,
                "version": target.version,
                "repos": [r.strip() for r in repos if r.strip()],
            }
        )
    return {
        "distros": distros,
        "include_cve": run.include_cve,
        "include_compliance": run.include_compliance,
        "iso_label": run.iso_label,
        "media_size_bytes": run.media_size_bytes,
    }


def _snapshot_paths_for_targets(db, run: models.AirgapCollectionRun) -> dict:
    """Build the per-target snapshot-dir map the engine needs.

    Returns ``{"<distro>:<version>": "<mirror_root>/<name>/.snapshots/<snap_id>/"}``.
    Empty value for any target whose snapshot row is missing — caller
    treats that as a fatal error.
    """
    settings_row = db.query(models.MirrorSettings).first()
    if settings_row is None or not settings_row.mirror_root_path:
        return {}
    mapping = {}
    for target in run.targets or []:
        if target.mirror is None or target.source_snapshot is None:
            mapping[f"{target.distro}:{target.version}"] = ""
            continue
        mapping[f"{target.distro}:{target.version}"] = (
            f"{settings_row.mirror_root_path}/{target.mirror.name}"
            f"/.snapshots/{target.source_snapshot.snapshot_id}/"
        )
    return mapping


def _targets_snapshot_state(
    run: models.AirgapCollectionRun,
) -> tuple[bool, list, list]:
    """Inspect each target's snapshot row and report readiness.

    Returns ``(all_ready, still_in_flight, failed)`` where:
      all_ready    = True iff every target has a snapshot whose
                     mirror cleared ``last_snapshot_message_id`` AND
                     the snapshot's row exists (not deleted on
                     failure).
      still_in_flight = list of mirror names still snapshotting.
      failed       = list of (mirror_name, error_text) tuples for
                     any target whose snapshot already FAILED.
    """
    still: list = []
    failed: list = []
    ready = True
    for target in run.targets or []:
        mirror = target.mirror
        if mirror is None:
            # Mirror was deleted between create_run and the tick.
            # Treat as failure so the operator gets a clear message.
            ready = False
            failed.append(("<deleted mirror>", "mirror row no longer exists"))
            continue
        if mirror.last_snapshot_message_id is not None:
            ready = False
            still.append(mirror.name)
            continue
        if mirror.last_snapshot_status == "FAILED":
            ready = False
            failed.append((mirror.name, mirror.last_snapshot_error or "unknown"))
            continue
        # No in-flight marker + status SUCCESS (or NULL on the rare
        # path where the agent reported success on a previously-NULL
        # row).  The MirrorSnapshot row we FK'd to must still exist;
        # _apply_mirror_sync_status deletes it only on failure.
        if target.source_snapshot is None:
            ready = False
            failed.append((mirror.name, "snapshot row missing despite SUCCESS status"))
    return ready, still, failed


def _mark_failed(run: models.AirgapCollectionRun, reason: str) -> None:
    """Transition a run to FAILED with a captured reason string.

    Always clears ``worker_message_id`` so the next tick doesn't think
    a plan is still in flight.  Idempotent: re-marking an already-
    failed run is a no-op (the original reason is preserved).
    """
    if run.status == STATUS_FAILED:
        return
    run.status = STATUS_FAILED
    run.error_message = reason[:8000]
    run.worker_message_id = None
    run.completed_at = _now_naive()


def _resolve_dispatch_host(db, run):
    """Run the QUEUED→MIRRORING gates and resolve the dispatch host.

    Encapsulates steps 1–2 of :func:`_advance_queued_to_mirroring`:
    validate targets/mirror_ids, apply the snapshot-readiness gate
    (leaving the run QUEUED when snapshots are still in flight, or
    FAILED when one blew up), then locate the shared dispatch host.

    Returns the ``Host`` to dispatch to, or ``None`` when the caller
    should stop this tick (either the run was marked FAILED, or it is
    intentionally left QUEUED to retry next tick).
    """
    if not run.targets:
        _mark_failed(
            run,
            "no targets configured on this run — add at least one "
            "target via the runs API before retrying",
        )
        return None
    if any(t.mirror_id is None for t in run.targets):
        _mark_failed(
            run,
            "one or more targets has no mirror_id; Option-B requires "
            "every target to be tied to a mirror_repository row",
        )
        return None

    # Snapshot readiness gate.  Leave QUEUED if any are still working,
    # flip to FAILED if any blew up.
    ready, still, failed = _targets_snapshot_state(run)
    if failed:
        joined = "; ".join(f"{name}: {err}" for name, err in failed)
        _mark_failed(run, f"target snapshot(s) failed — {joined}")
        return None
    if not ready:
        # In-flight; come back next tick.  Log on a coarse interval
        # to avoid spamming when the snapshot takes a long time.
        logger.debug(
            "airgap run %s waiting on snapshots: %s",
            run.id,
            ", ".join(still),
        )
        return None

    # All snapshots ready — figure out which host to dispatch to.
    # In Option-B every target shares the same mirror.host_id (the
    # create_run endpoint validates this) so any target's host is
    # the right one.
    first_target = run.targets[0]
    host_id = first_target.mirror.host_id if first_target.mirror else None
    if host_id is None:
        _mark_failed(
            run,
            "first target's mirror has no host_id — mirror was deleted?",
        )
        return None
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if host is None:
        _mark_failed(
            run,
            f"host {host_id} for the target mirrors no longer exists",
        )
        return None
    return host


def _compute_target_sizing(run):
    """Sum per-target snapshot sizes for the disc-fit decision.

    rsync ``--stats`` populated each snapshot's ``size_bytes`` at
    completion, so we have authoritative numbers without spawning a
    sizing query.  A target with NULL size_bytes (older agent, missing
    --stats parse, etc.) is treated as "size unknown" and the run falls
    through to single-disc; the rsync just won't fit if it overflows
    but at least we tried.

    Returns ``(target_sizes, total_bytes, unknown_size)``.
    """
    target_sizes = {}
    total_bytes = 0
    unknown_size = False
    for target in run.targets:
        size = (
            target.source_snapshot.size_bytes
            if target.source_snapshot is not None
            else None
        )
        if size is None:
            unknown_size = True
            continue
        key = (target.distro, target.version)
        target_sizes[key] = size
        total_bytes += size
    return target_sizes, total_bytes, unknown_size


def _build_multidisc_plan(
    engine, run, req, source_snapshots, target_sizes, total_bytes, media_size
):
    """Build the multi-disc collection plan, or mark the run FAILED.

    Returns the plan dict, or ``None`` when the engine lacks the
    multi-disc builder or the build raised (both mark the run FAILED).
    """
    multidisc_builder = getattr(
        engine, "build_snapshot_multidisc_collection_plan", None
    )
    if multidisc_builder is None:
        _mark_failed(
            run,
            f"snapshot tree ({total_bytes} bytes) exceeds disc "
            f"size ({media_size}) but airgap_collector_engine."
            "build_snapshot_multidisc_collection_plan is missing. "
            "Rebuild the Pro+ Cython modules.",
        )
        return None
    # Sign one manifest envelope; the engine stamps each disc's
    # own disc_index/disc_count onto a copy.  Same signed
    # payload the single-disc path embeds — so a multi-disc
    # bundle passes the repository's strict verify too.
    multidisc_manifest = {
        "format_version": 1,
        "iso_label": run.iso_label,
        "include_cve": run.include_cve,
        "include_compliance": run.include_compliance,
        "targets": _manifest_targets(run),
    }
    signed_envelope = _sign_manifest_or_raw(engine, multidisc_manifest)
    try:
        plan = multidisc_builder(
            req,
            source_snapshots=source_snapshots,
            target_sizes=target_sizes,
            # Disc files land at /var/lib/sysmanage/airgap-iso/
            # <run.id>-disc-<N>.iso so the download endpoint can
            # locate them by run id alone.
            iso_path_prefix=str(run.id),
            staging_root=f"/var/lib/sysmanage/airgap-staging/{run.id}",
            manifest_envelope=signed_envelope,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # CollectorConfigError raised when a single target
        # exceeds disc size; surface verbatim so the operator
        # sees which target is too big.
        _mark_failed(run, f"multi-disc plan build failed: {exc}")
        return None
    logger.info(
        "airgap run %s using multi-disc plan: %d bytes across discs",
        run.id,
        total_bytes,
    )
    return plan


def _build_single_disc_plan(engine, run, req, source_snapshots):
    """Build the single-disc collection plan (or legacy fallback)."""
    single_builder = getattr(engine, "build_snapshot_collection_run_plan", None)
    if single_builder is None:
        logger.warning(
            "airgap_collector_engine.build_snapshot_collection_"
            "run_plan missing; falling back to legacy upstream-"
            "fetch plan for run %s",
            run.id,
        )
        return engine.build_collection_run_plan(req)
    # CRITICAL: pass the SAME run-id-scoped staging root that
    # the ISO-build stage reads from
    # (_advance_staging_complete_to_building_iso ->
    # staging_dir=/var/lib/sysmanage/airgap-staging/<run.id>).
    # Without this the engine defaults staging_root to the bare
    # /var/lib/sysmanage/airgap-staging, so the packages land in
    # .../airgap-staging/<target>/ while xorriso later bundles the
    # empty .../airgap-staging/<run.id>/ -> a manifest-only
    # (hollow) ISO.  The multi-disc path above already scopes by
    # run.id; the single-disc path must match it.
    return single_builder(
        req,
        source_snapshots=source_snapshots,
        staging_root=f"/var/lib/sysmanage/airgap-staging/{run.id}",
    )


def _advance_queued_to_mirroring(db, run, engine) -> None:
    """Wait for per-target snapshots; then dispatch snapshot-sourced plan.

    Option-B advancement:
      1. Validate the run has targets and they all have a mirror_id.
      2. Inspect each target mirror's snapshot state.  If any is still
         in flight → leave the run at QUEUED (next tick checks again).
         If any FAILED → flip the run to FAILED with the surfaced
         error so the operator sees what to fix.
      3. Build a snapshot-sourced collection plan via the engine's
         ``build_snapshot_collection_run_plan`` — the plan rsyncs
         each target's snapshot dir into the staging tree.
      4. Dispatch to the mirror's host (all targets share one host
         per create_run validation).  Status → MIRRORING.
    """
    host = _resolve_dispatch_host(db, run)
    if host is None:
        return

    try:
        req = _build_collection_request(run)
        source_snapshots = _snapshot_paths_for_targets(db, run)
        if any(not v for v in source_snapshots.values()):
            _mark_failed(
                run,
                "could not resolve snapshot path for one or more "
                "targets; mirror_settings.mirror_root_path may be unset",
            )
            return
        # Decide single-disc vs multi-disc up front based on total
        # snapshot size.
        media_size = int(run.media_size_bytes or 4_700_000_000)
        target_sizes, total_bytes, unknown_size = _compute_target_sizing(run)
        need_multidisc = not unknown_size and total_bytes > media_size and target_sizes

        # A run with no ``burn_device`` produces a downloadable ISO meant to
        # be attached as virtual media (e.g. a VM's CD/DVD drive), which has
        # no physical single-disc size limit.  Multi-disc splitting exists
        # only to fit physical media — and v0.1.0 can't file-split a single
        # oversize repo anyway — so when nobody is burning a disc, always
        # emit ONE ISO regardless of size instead of failing the disc-fit
        # check.  The single-disc builder below has no size cap; xorriso /
        # UDF handle multi-GB ISOs fine.
        if run.burn_device is None:
            need_multidisc = False

        if need_multidisc:
            plan = _build_multidisc_plan(
                engine,
                run,
                req,
                source_snapshots,
                target_sizes,
                total_bytes,
                media_size,
            )
            if plan is None:
                return
            stage = "multidisc"
            timeout = 28800  # multi-hour for big bundles
        else:
            plan = _build_single_disc_plan(engine, run, req, source_snapshots)
            stage = "mirroring"
            timeout = 14400
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _mark_failed(run, f"plan build failed: {exc}")
        return
    try:
        # Late import: proplus_dispatch imports module_loader at top
        # level so eager-importing it here creates an import cycle
        # during startup before module_loader has finished its scan.
        from backend.services.proplus_dispatch import (  # pylint: disable=import-outside-toplevel
            enqueue_apply_plan,
            register_airgap_run_correlation,
        )

        msg_id = enqueue_apply_plan(host_id=str(host.id), plan=plan, timeout=timeout)
        register_airgap_run_correlation(msg_id, stage, str(run.id), str(host.id))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _mark_failed(run, f"plan dispatch failed: {exc}")
        return
    # Multi-disc plans do staging AND ISO build inline, so the run
    # jumps to BUILDING_ISO and the result handler advances it to
    # ISO_BUILT in one shot.  Single-disc plans stop at staging
    # (rsync only); the orchestrator dispatches build_iso_plan as a
    # follow-up.
    run.status = STATUS_BUILDING_ISO if need_multidisc else STATUS_MIRRORING
    run.started_at = _now_naive()
    run.worker_message_id = msg_id
    run.error_message = None


def _advance_staging_complete_to_building_iso(db, run, engine) -> None:
    """Dispatch an ISO-build plan and flip STAGING_COMPLETE → BUILDING_ISO."""
    host = _find_collector_host(db)
    if host is None:
        _mark_failed(
            run,
            "could not find a registered Host to dispatch the ISO build to",
        )
        return
    try:
        manifest = {
            "format_version": 1,
            "iso_label": run.iso_label,
            "include_cve": run.include_cve,
            "include_compliance": run.include_compliance,
            "targets": _manifest_targets(run),
        }
        # Sign the manifest before embedding it.  The repository side
        # verifies the ``/manifest.json`` that lives ON the disc (not
        # the collector's DB row), and its ingest runs strict by
        # default — an unsigned manifest is rejected at the air-gap
        # crossing.  ``_sign_manifest_or_raw`` returns a signed envelope
        # when the collector key is present, or the bare manifest (with
        # a logged warning) when it isn't, so a misconfigured collector
        # produces a downloadable-but-unverifiable ISO rather than a
        # hard failure mid-run.
        manifest_payload = _sign_manifest_or_raw(engine, manifest)
        plan = engine.build_iso_plan(
            staging_dir=f"/var/lib/sysmanage/airgap-staging/{run.id}",
            output_iso=f"/var/lib/sysmanage/airgap-iso/{run.id}.iso",
            manifest_dict=manifest_payload,
            iso_label=run.iso_label,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _mark_failed(run, f"ISO plan build failed: {exc}")
        return

    # The engine's build_iso_plan writes the ISO to
    # /var/lib/sysmanage/airgap-iso/<id>.iso but never creates that parent
    # directory, and xorriso/libburn refuse to create it themselves
    # ("Neither stdio-path nor its directory exist") — so the build fails
    # on any collector host where the dir doesn't already exist.  Prepend a
    # mkdir to the plan so the output dir is guaranteed before xorriso runs
    # (mkdir is already in the agent's sudoers allowlist).
    if isinstance(plan, dict) and isinstance(plan.get("commands"), list):
        plan["commands"].insert(
            0,
            {
                "argv": ["sudo", "mkdir", "-p", "/var/lib/sysmanage/airgap-iso"],
                "description": "ensure ISO output dir exists",
            },
        )

    try:
        from backend.services.proplus_dispatch import (  # pylint: disable=import-outside-toplevel
            enqueue_apply_plan,
            register_airgap_run_correlation,
        )

        msg_id = enqueue_apply_plan(host_id=str(host.id), plan=plan, timeout=7200)
        register_airgap_run_correlation(
            msg_id, "building_iso", str(run.id), str(host.id)
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _mark_failed(run, f"ISO plan dispatch failed: {exc}")
        return
    run.status = STATUS_BUILDING_ISO
    run.worker_message_id = msg_id
    run.error_message = None


def _advance_iso_built_to_complete(run) -> None:
    """Final state transition: ISO is on disk, mark the run COMPLETE.

    Only called when ``burn_device`` is NULL — when set, the run
    detours through BURNING via ``_advance_iso_built_to_burning``.
    """
    run.status = STATUS_COMPLETE
    run.completed_at = _now_naive()
    run.worker_message_id = None


def _advance_iso_built_to_burning(db, run, engine) -> None:
    """Dispatch a burn plan and flip ISO_BUILT → BURNING.

    ``run.burn_device`` is the validated device path (e.g.
    ``/dev/sr0``); the engine's ``build_burn_plan`` wraps cdrecord /
    growisofs with that target.  On result the run advances to
    COMPLETE via ``_apply_airgap_run_result``.
    """
    host = _find_collector_host(db)
    if host is None:
        _mark_failed(
            run,
            "could not find a registered Host to dispatch the burn plan to",
        )
        return
    try:
        plan = engine.build_burn_plan(
            iso_path=f"/var/lib/sysmanage/airgap-iso/{run.id}.iso",
            device=run.burn_device,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _mark_failed(run, f"burn plan build failed: {exc}")
        return
    try:
        from backend.services.proplus_dispatch import (  # pylint: disable=import-outside-toplevel
            enqueue_apply_plan,
            register_airgap_run_correlation,
        )

        msg_id = enqueue_apply_plan(host_id=str(host.id), plan=plan, timeout=7200)
        register_airgap_run_correlation(msg_id, "burning", str(run.id), str(host.id))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _mark_failed(run, f"burn plan dispatch failed: {exc}")
        return
    run.status = STATUS_BURNING
    run.worker_message_id = msg_id
    run.error_message = None


def _dispatch_run_advance(db, run, engine) -> None:
    """Drive the single state transition appropriate for ``run.status``.

    Pure dispatch on the run's current status — the caller owns the
    surrounding skip-inflight check, the FAILED/advanced tallying, and
    the per-run exception handling.
    """
    if run.status == STATUS_QUEUED:
        _advance_queued_to_mirroring(db, run, engine)
    elif run.status == STATUS_STAGING_COMPLETE:
        _advance_staging_complete_to_building_iso(db, run, engine)
    elif run.status == STATUS_ISO_BUILT:
        # Branch on burn_device: with it set we dispatch a burn plan to
        # an agent that has access to the optical device.  Without it,
        # ISO_BUILT IS the done-state and we shortcut to COMPLETE.
        if run.burn_device:
            _advance_iso_built_to_burning(db, run, engine)
        else:
            _advance_iso_built_to_complete(run)


def _advance_one_run(db, run, engine, summary: dict) -> None:
    """Advance a single run row and update ``summary`` in place.

    Skips rows still carrying a ``worker_message_id`` (defense-in-depth
    against a crashed result handler re-dispatching), then runs the
    status-appropriate transition and tallies the outcome.
    """
    # Defense-in-depth: skip rows that still carry a non-NULL
    # ``worker_message_id`` — the result handler should have cleared it
    # before the row could land in a ready-to-advance state, but if it
    # didn't (race with a crashed handler), don't re-dispatch.
    if run.worker_message_id is not None:
        summary["skipped_inflight"] += 1
        return
    try:
        _dispatch_run_advance(db, run, engine)
        if run.status == STATUS_FAILED:
            summary["failed"] += 1
        else:
            summary["advanced"] += 1
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("airgap run tick failed for run %s: %s", run.id, exc)
        _mark_failed(run, f"tick exception: {exc}")
        summary["failed"] += 1


def _run_one_tick() -> dict:
    """Advance every AirgapCollectionRun that's ready to progress."""
    summary = {"advanced": 0, "failed": 0, "skipped_inflight": 0}
    engine = module_loader.get_module("airgap_collector_engine")
    if engine is None:
        return summary

    db = next(get_db())
    try:
        # Pick up runs whose status is one of the "ready to advance"
        # values.  Runs in MIRRORING / BUILDING_ISO are mid-flight and
        # waited on by the result handler, not this tick.
        rows = (
            db.query(models.AirgapCollectionRun)
            .filter(
                models.AirgapCollectionRun.status.in_(
                    [STATUS_QUEUED, STATUS_STAGING_COMPLETE, STATUS_ISO_BUILT]
                )
            )
            .all()
        )
        for run in rows:
            _advance_one_run(db, run, engine, summary)
        if rows:
            db.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("airgap run tick batch failed")
        db.rollback()
    finally:
        db.close()
    return summary


async def airgap_run_tick_service() -> None:
    """Background service: advance every collection run every TICK_INTERVAL_SECONDS.

    Started from ``backend/startup/lifecycle.py`` only when the
    ``airgap_collector_engine`` Pro+ module is loaded — same gate as
    the schedule-tick.
    """
    logger.info(
        "Starting air-gap collection run tick service (interval=%ds)",
        TICK_INTERVAL_SECONDS,
    )
    while True:
        try:
            summary = _run_one_tick()
            if summary["advanced"] or summary["failed"]:
                logger.info(
                    "Air-gap run tick: advanced=%d failed=%d skipped_inflight=%d",
                    summary["advanced"],
                    summary["failed"],
                    summary["skipped_inflight"],
                )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Air-gap run tick service cancelled")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("airgap run tick service outer loop error")
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)
