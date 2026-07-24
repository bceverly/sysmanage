# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content-lifecycle engine-path result-apply handlers (Phase 16).

Extracted from ``backend.services.proplus_dispatch`` to keep that module under
pylint's max-module-lines cap; re-imported there and registered in
``_SIMPLE_RESULT_HANDLERS`` under ``"content_lifecycle_op"``.

These handlers translate a completed ``content_lifecycle_engine`` plan
``outcome`` into database state.  Two actions are defined:

* ``publish_materialize`` — stamp a ``SharedContentViewVersion``
  published/failed and, on success, bind the Library environment to the new
  version (the entry point of the promotion path) + run pin-aware retention GC.
* ``reclaim`` — a best-effort store removal for a GC'd version; the row was
  already marked ``deprecated`` at dispatch time, so we only log the outcome.

Content-view versions live in the SHARED partition, so we acquire a
``shared_sessionmaker()`` session; the promotion bindings/audit live in the
TENANT partition, resolved from the reporting host (Slice 4).

A couple of dispatch primitives (``_now_naive``, ``_best_failure_text``) live in
``proplus_dispatch`` and are imported lazily to avoid a circular import at load.
"""

import logging
from typing import Any, Dict

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.models.content_lifecycle import (
    CVV_DEPRECATED,
    CVV_FAILED,
    CVV_PUBLISHED,
    PROMOTION_PUBLISH,
)
from backend.persistence.partitions import shared_sessionmaker

logger = logging.getLogger(__name__)


def _publish_manifest(
    outcome: Dict[str, Any], existing: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Compact record stored on the published version's ``manifest`` column.

    The per-file SHA manifest is materialized on the mirror host; here we keep a
    lightweight summary (command count + terminal status) so the UI/audit can
    show what ran without hauling the full file list back over the wire.  Merges
    over any manifest set at publish-request time (e.g. a composite version's
    resolved component list, Slice 6), so that context survives.
    """
    commands = outcome.get("commands") or []
    data = dict(existing or {})
    data["command_count"] = len(commands)
    data["outcome_status"] = outcome.get("status")
    return data


def _tenant_session_for_host(host_id: str):
    """Open a session on the database that actually holds ``host_id``.

    Mirrors ``proplus_dispatch``'s outbound routing: resolve the host's tenant
    engine (the host->tenant index works in background context) and fall back to
    the request engine, which collapses to the bootstrap engine in single-tenant
    mode.  The promotion bindings/audit are TENANT-partition rows.
    """
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence.partitions import (  # noqa: PLC0415
        get_request_engine,
        tenant_engine_for_host,
    )

    engine = tenant_engine_for_host(host_id) or get_request_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _pinned_version_ids(tenant_session, cv_id) -> set:
    """Every version id a binding references for this CV — both the currently
    bound version AND each binding's ``previous_version_id`` (the rollback
    target).  A pinned version is NEVER reclaimed."""
    pinned = set()
    rows = (
        tenant_session.query(models.EnvironmentContentBinding)
        .filter(models.EnvironmentContentBinding.content_view_id == cv_id)
        .all()
    )
    for binding in rows:
        pinned.add(str(binding.content_view_version_id))
        if binding.previous_version_id:
            pinned.add(str(binding.previous_version_id))
    return pinned


def _bind_library(tenant_session, shared_session, row):
    """Bind the Library environment to the freshly published version (the path
    root / promotion source) and append a publish audit row.  Flushes so the new
    binding is visible to the pin-aware GC that follows.  Returns the Library
    environment name (so the caller can repoint its serving symlink), or None."""
    library = (
        shared_session.query(models.SharedLifecycleEnvironment)
        .filter(models.SharedLifecycleEnvironment.is_library.is_(True))
        .first()
    )
    if library is None:
        logger.warning(
            "content_lifecycle publish: no Library environment; cannot bind cv %s",
            row.content_view_id,
        )
        return None

    from backend.services.proplus_dispatch import _now_naive  # noqa: PLC0415

    binding = (
        tenant_session.query(models.EnvironmentContentBinding)
        .filter(models.EnvironmentContentBinding.environment_id == library.id)
        .filter(models.EnvironmentContentBinding.content_view_id == row.content_view_id)
        .first()
    )
    if binding is None:
        binding = models.EnvironmentContentBinding(
            environment_id=library.id,
            content_view_id=row.content_view_id,
            content_view_version_id=row.id,
        )
        tenant_session.add(binding)
    else:
        if str(binding.content_view_version_id) != str(row.id):
            binding.previous_version_id = binding.content_view_version_id
        binding.content_view_version_id = row.id
        binding.promoted_at = _now_naive()

    tenant_session.add(
        models.ContentPromotionAudit(
            content_view_id=row.content_view_id,
            to_environment_id=library.id,
            content_view_version_id=row.id,
            action=PROMOTION_PUBLISH,
            at=_now_naive(),
        )
    )
    tenant_session.flush()
    return library.name


def dispatch_env_symlink(host_id, mirror_root, cv_id, env_name, version) -> None:
    """Repoint an environment's serving symlink to a version on the mirror host.

    The physical half of a DB rebind (publish/promote/rollback, Slice 5): the
    stable URL ``/content-views/{cv}/{env}`` is a symlink the mirror host swaps to
    the newly-bound version.  Best-effort + loudly logged -- the store-and-forward
    queue delivers it and a re-promote reconciles, so a dispatch hiccup must not
    fail the (already-committed) rebind."""
    engine = module_loader.get_module("content_lifecycle_engine")
    if engine is None:
        logger.warning(
            "content_lifecycle: engine not loaded; cannot repoint cv=%s env=%s",
            cv_id,
            env_name,
        )
        return
    try:
        plan = engine.build_set_env_symlink_plan(mirror_root, cv_id, env_name, version)
        from backend.services.proplus_dispatch import (  # noqa: PLC0415
            enqueue_apply_plan,
            register_content_lifecycle_correlation,
        )

        msg_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=120)
        register_content_lifecycle_correlation(
            msg_id, "set_env_symlink", str(host_id), str(cv_id)
        )
        logger.info(
            "content_lifecycle: env repoint dispatched cv=%s env=%s -> v%s (host %s)",
            cv_id,
            env_name,
            version,
            host_id,
        )
    except Exception:  # noqa: BLE001 - serving repoint is best-effort
        logger.exception(
            "content_lifecycle: failed to dispatch env symlink cv=%s env=%s",
            cv_id,
            env_name,
        )


def _reclaim_version(shared_session, engine, version, host_id) -> None:
    """Deprecate one version and dispatch a best-effort store removal.  The row
    is marked ``deprecated`` immediately; the physical ``rm`` is fire-and-schedule
    (its result only logs — the version history row is retained)."""
    store_path = version.store_path
    version.status = CVV_DEPRECATED
    version.store_path = None
    shared_session.commit()
    if not store_path or engine is None:
        return
    try:
        plan = engine.build_reclaim_version_plan(store_path)
        from backend.services.proplus_dispatch import (  # noqa: PLC0415
            enqueue_apply_plan,
            register_content_lifecycle_correlation,
        )

        msg_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=1800)
        register_content_lifecycle_correlation(
            msg_id, "reclaim", str(host_id), str(version.id)
        )
        logger.info(
            "content view version %s reclaimed (store removal dispatched, host %s)",
            version.id,
            host_id,
        )
    except Exception:  # noqa: BLE001 - GC is best-effort; never fail the publish
        logger.exception(
            "content_lifecycle: failed to dispatch reclaim for version %s",
            version.id,
        )


def _reap_unpinned_versions(shared_session, tenant_session, row, host_id) -> None:
    """Retention GC: reclaim published versions beyond the CV's ``keep_versions``
    that no binding pins.  Never touches the newest ``keep_versions`` and never a
    pinned (bound or rollback-target) version — that is the rollback guarantee."""
    cv = (
        shared_session.query(models.SharedContentView)
        .filter(models.SharedContentView.id == row.content_view_id)
        .first()
    )
    if cv is None:
        return
    published = sorted(
        (v for v in cv.versions if v.status == CVV_PUBLISHED),
        key=lambda v: v.version,
        reverse=True,
    )
    candidates = published[cv.keep_versions :]
    if not candidates:
        return
    pinned = _pinned_version_ids(tenant_session, cv.id)
    engine = module_loader.get_module("content_lifecycle_engine")
    for version in candidates:
        if str(version.id) in pinned:
            continue
        _reclaim_version(shared_session, engine, version, host_id)


def _finalize_publish(shared_session, row, host_id) -> None:
    """Post-publish side effects: bind Library -> new version + pin-aware GC.

    Best-effort and heavily logged — the version is already committed
    ``published`` before we get here, so a hiccup binding or reaping must never
    unwind that."""
    try:
        with _tenant_session_for_host(host_id) as tenant_session:
            library_name = _bind_library(tenant_session, shared_session, row)
            _reap_unpinned_versions(shared_session, tenant_session, row, host_id)
            tenant_session.commit()
        # Repoint the Library serving symlink at the freshly published version so
        # the content is actually served (Slice 5).  ``store_path`` is
        # ``{mirror_root}/.content-views/{cv}/v{n}`` -> recover the mirror root.
        if library_name and row.store_path:
            mirror_root = row.store_path.rsplit("/.content-views/", 1)[0]
            dispatch_env_symlink(
                host_id, mirror_root, row.content_view_id, library_name, row.version
            )
    except Exception:  # noqa: BLE001 - side effects must not corrupt published state
        logger.exception(
            "content_lifecycle: publish finalize failed for version %s (host %s)",
            row.id,
            host_id,
        )


def _apply_publish_result(cvv_id: str, host_id: str, outcome: Dict[str, Any]) -> None:
    """Stamp the ``SharedContentViewVersion`` published/failed; on success run the
    Library-binding + retention finalize."""
    from backend.services.proplus_dispatch import (  # noqa: PLC0415
        _best_failure_text,
        _now_naive,
    )

    session_local = shared_sessionmaker()
    with session_local() as session:
        row = (
            session.query(models.SharedContentViewVersion)
            .filter(models.SharedContentViewVersion.id == cvv_id)
            .first()
        )
        if row is None:
            logger.info(
                "SharedContentViewVersion %s no longer exists; dropping publish result",
                cvv_id,
            )
            return

        succeeded = outcome.get("status") == "succeeded"
        if succeeded:
            row.status = CVV_PUBLISHED
            row.published_at = _now_naive()
            row.publish_error = None
            row.manifest = _publish_manifest(outcome, row.manifest)
            session.commit()
            _finalize_publish(session, row, host_id)
        else:
            row.status = CVV_FAILED
            row.publish_error = _best_failure_text(outcome)[:8000]
            session.commit()
        logger.info(
            "content view version %s publish -> %s (host %s)",
            cvv_id,
            row.status,
            host_id,
        )


def _log_reclaim_result(cvv_id: str, host_id: str, outcome: Dict[str, Any]) -> None:
    """A reclaim plan finished; the row is already ``deprecated`` so we only log
    (loudly on failure — orphaned bytes are worth a warning)."""
    if outcome.get("status") == "succeeded":
        logger.info(
            "content view version %s store reclaimed on host %s", cvv_id, host_id
        )
        return
    from backend.services.proplus_dispatch import _best_failure_text  # noqa: PLC0415

    logger.warning(
        "content view version %s store reclaim FAILED on host %s: %s",
        cvv_id,
        host_id,
        _best_failure_text(outcome)[:500],
    )


# Serving-side ops (Slice 5) carry no DB state to update on completion -- the
# authoritative state (binding / assignment) was committed before dispatch -- so
# their result handling is log-only, loud on failure.
_LOG_ONLY_OPS = {
    "set_env_symlink": "environment serving repoint",
    "serve_content": "mirror-host serving provision",
    "repoint": "client repoint",
    "repoint_snaps": "client snap repoint",
}


def _log_op_result(
    action: str, ref: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Log the outcome of a serving-side op (symlink repoint / serve / repoint)."""
    label = _LOG_ONLY_OPS.get(action, action)
    if outcome.get("status") == "succeeded":
        logger.info(
            "content_lifecycle: %s succeeded (%s, host %s)", label, ref, host_id
        )
        return
    from backend.services.proplus_dispatch import _best_failure_text  # noqa: PLC0415

    logger.warning(
        "content_lifecycle: %s FAILED (%s, host %s): %s",
        label,
        ref,
        host_id,
        _best_failure_text(outcome)[:500],
    )


def _apply_cv_export_result(
    export_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Flip a ``ContentViewExportRun`` COMPLETE/FAILED when its ISO build finishes
    on the mirror host (Slice 7a)."""
    from backend.persistence.models.content_lifecycle import (  # noqa: PLC0415
        EXPORT_COMPLETE,
        EXPORT_FAILED,
    )
    from backend.services.proplus_dispatch import (  # noqa: PLC0415
        _best_failure_text,
        _now_naive,
    )

    with _tenant_session_for_host(host_id) as session:
        run = (
            session.query(models.ContentViewExportRun)
            .filter(models.ContentViewExportRun.id == export_id)
            .first()
        )
        if run is None:
            logger.info(
                "ContentViewExportRun %s no longer exists; dropping export result",
                export_id,
            )
            return
        run.worker_message_id = None
        run.completed_at = _now_naive()
        if outcome.get("status") == "succeeded":
            run.status = EXPORT_COMPLETE
            run.error_message = None
        else:
            run.status = EXPORT_FAILED
            run.error_message = _best_failure_text(outcome)[:8000]
        session.commit()
        logger.info(
            "content view export %s -> %s (host %s)", export_id, run.status, host_id
        )


def _apply_cv_pull_result(cmd_id: str, host_id: str, outcome: Dict[str, Any]) -> None:
    """Site side (Slice 7b): flip the ``content_view_sync`` received-command
    COMPLETE/FAILED when its HTTP-pull plan finishes on the site's mirror host.
    The site's report-back worker then acks the coordinator."""
    from backend.services import federation_inbox_service as inbox  # noqa: PLC0415

    with _tenant_session_for_host(host_id) as session:
        try:
            if outcome.get("status") == "succeeded":
                inbox.update_command_status(
                    session,
                    cmd_id,
                    new_status=inbox.CMD_STATUS_COMPLETED,
                    result={"ok": True},
                )
            else:
                from backend.services.proplus_dispatch import (
                    _best_failure_text,
                )  # noqa: PLC0415

                inbox.update_command_status(
                    session,
                    cmd_id,
                    new_status=inbox.CMD_STATUS_FAILED,
                    result={"error": _best_failure_text(outcome)[:500]},
                )
            session.commit()
            logger.info(
                "content_lifecycle: site pull for command %s -> %s (host %s)",
                cmd_id,
                outcome.get("status"),
                host_id,
            )
        except Exception:  # noqa: BLE001 - result routing must not crash the tick
            logger.exception(
                "content_lifecycle: cv_pull result update failed for command %s",
                cmd_id,
            )


def _packages(stdout) -> set:
    """Package basenames from a ``list packages`` command's stdout."""
    return {line.strip() for line in (stdout or "").splitlines() if line.strip()}


def _apply_cv_diff_result(cvv_id: str, host_id: str, outcome: Dict[str, Any]) -> None:
    """Version diff (Slice 8): the plan listed the previous + current version
    stores' packages (commands ``[previous, current]``); compare their stdouts
    and store added/removed on the current version's ``manifest``."""
    commands = outcome.get("commands") or []
    if len(commands) < 2:
        logger.warning(
            "content_lifecycle diff: expected 2 command outputs, got %d (cvv %s)",
            len(commands),
            cvv_id,
        )
        return
    prev = _packages(commands[0].get("stdout"))
    cur = _packages(commands[1].get("stdout"))
    added = sorted(cur - prev)[:2000]
    removed = sorted(prev - cur)[:2000]

    from backend.services.proplus_dispatch import _now_naive  # noqa: PLC0415

    session_local = shared_sessionmaker()
    with session_local() as session:
        row = (
            session.query(models.SharedContentViewVersion)
            .filter(models.SharedContentViewVersion.id == cvv_id)
            .first()
        )
        if row is None:
            logger.info("SharedContentViewVersion %s gone; dropping diff", cvv_id)
            return
        manifest = dict(row.manifest or {})
        manifest["diff_from_prev"] = {
            "added": added,
            "removed": removed,
            "added_count": len(added),
            "removed_count": len(removed),
            "at": _now_naive().isoformat(),
        }
        row.manifest = manifest  # reassign so SQLAlchemy tracks the JSON change
        session.commit()
        logger.info(
            "content view version %s diff: +%d -%d (host %s)",
            cvv_id,
            len(added),
            len(removed),
            host_id,
        )


def _apply_content_lifecycle_op_result(
    primary_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Route a completed ``content_lifecycle_engine`` plan by its action.

    ``primary_id`` is ``"<action>:<cvv_id>"``.
    """
    if ":" not in primary_id:
        action, cvv_id = primary_id, ""
    else:
        action, cvv_id = primary_id.split(":", 1)

    if action == "publish_materialize" and cvv_id:
        _apply_publish_result(cvv_id, host_id, outcome)
    elif action == "reclaim" and cvv_id:
        _log_reclaim_result(cvv_id, host_id, outcome)
    elif action == "cv_export" and cvv_id:
        _apply_cv_export_result(cvv_id, host_id, outcome)
    elif action == "cv_pull" and cvv_id:
        _apply_cv_pull_result(cvv_id, host_id, outcome)
    elif action == "cv_diff" and cvv_id:
        _apply_cv_diff_result(cvv_id, host_id, outcome)
    elif action in _LOG_ONLY_OPS:
        _log_op_result(action, cvv_id, host_id, outcome)
    else:
        # Never silently drop an unroutable result — log it with context.
        logger.warning(
            "content_lifecycle result: unhandled primary_id %r (host %s)",
            primary_id,
            host_id,
        )
