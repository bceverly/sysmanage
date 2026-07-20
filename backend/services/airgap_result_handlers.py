# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Air-gap collection/ingestion engine-path result-apply handlers.

Extracted from ``backend.services.proplus_dispatch`` to keep that module under
pylint's max-module-lines cap.  Both handlers are re-imported back into
``proplus_dispatch`` under their original private name, so the result-router and
its ``_SIMPLE_RESULT_HANDLERS`` table are unchanged.

``_best_failure_text`` / ``_now_naive`` live in ``proplus_dispatch`` and are
imported lazily inside the functions that need them to avoid a circular import
at module load.
"""

import logging
from typing import Any, Dict

from backend.persistence import db, models

logger = logging.getLogger(__name__)


def _apply_airgap_run_result(
    primary_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Handle completion of an air-gap collection-run plan.

    ``primary_id`` is ``"<stage>:<run_id>"``.  The stage drives the
    state transition:

      mirroring     → MIRRORING -> STAGING_COMPLETE on success,
                                  -> FAILED on failure.  The
                                  airgap_run_tick will pick up
                                  STAGING_COMPLETE on its next pass
                                  and dispatch the ISO plan.
      building_iso  → BUILDING_ISO -> ISO_BUILT on success.
                                     airgap_run_tick then advances
                                     ISO_BUILT -> COMPLETE.

    Always clears ``worker_message_id`` so the orchestrator's "is a
    plan in flight on this row?" check resets correctly.
    """
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _best_failure_text, _now_naive

    _ = host_id  # not used in row update; logged elsewhere for audit
    if ":" not in primary_id:
        logger.warning(
            "airgap_run result with malformed primary_id %r — dropping",
            primary_id,
        )
        return
    stage, run_id = primary_id.split(":", 1)

    session_local = db.get_session_local()
    with session_local() as session:
        run = (
            session.query(models.AirgapCollectionRun)
            .filter(models.AirgapCollectionRun.id == run_id)
            .first()
        )
        if run is None:
            logger.info(
                "airgap collection run %s no longer exists; dropping %s result",
                run_id,
                stage,
            )
            return

        succeeded = outcome["status"] == "succeeded"
        run.worker_message_id = None

        if not succeeded:
            run.status = "FAILED"
            run.error_message = _best_failure_text(outcome)[:8000]
            run.completed_at = _now_naive()
            session.commit()
            return

        if stage == "mirroring":
            run.status = "STAGING_COMPLETE"
            run.error_message = None
        elif stage in ("building_iso", "multidisc"):
            # ``multidisc`` does staging AND ISO build inline per disc;
            # success means all per-disc ISOs are on disk.  Both stages
            # skip STAGING_COMPLETE and advance straight to ISO_BUILT so
            # the operator's "is my ISO ready?" check is uniform across
            # the single-disc and multi-disc paths.
            run.status = "ISO_BUILT"
            run.error_message = None
        elif stage == "burning":
            # The burn plan is the last stage in the lifecycle when
            # ``burn_device`` is set — go straight to COMPLETE rather
            # than detouring back through the tick.
            run.status = "COMPLETE"
            run.completed_at = _now_naive()
            run.error_message = None
        else:
            logger.warning(
                "airgap_run result with unknown stage %r (run_id=%s); leaving row at %s",
                stage,
                run_id,
                run.status,
            )
        session.commit()


def _apply_airgap_ingest_result(
    primary_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Handle completion of a repository-side ingestion plan.

    ``primary_id`` is ``"<stage>:<run_id>"``.  The stage drives the
    transition:

      mount → on success, hand the mount outcome to
              ``airgap_ingest_tick.process_mount_result`` (verifies the
              embedded manifest against the trusted keyring; sets
              VERIFIED on a good signature, FAILED otherwise).  The
              ingest tick then picks up VERIFIED and dispatches the copy.
      copy  → on success, ``process_copy_result`` sets COMPLETE,
              records rsync counts, and registers per-distro repos.

    Always clears ``worker_message_id`` so the orchestrator's in-flight
    check resets.  A failed agent plan short-circuits to FAILED with the
    best available stderr.
    """
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _best_failure_text, _now_naive

    _ = host_id  # logged elsewhere for audit; not needed for the row update
    if ":" not in primary_id:
        logger.warning(
            "airgap_ingest result with malformed primary_id %r — dropping",
            primary_id,
        )
        return
    stage, run_id = primary_id.split(":", 1)

    # Late import: the orchestrator late-imports proplus_dispatch for
    # dispatch helpers, so importing it at module top here would cycle.
    from backend.services import (  # pylint: disable=import-outside-toplevel
        airgap_ingest_tick,
    )

    session_local = db.get_session_local()
    with session_local() as session:
        run = (
            session.query(models.AirgapIngestionRun)
            .filter(models.AirgapIngestionRun.id == run_id)
            .first()
        )
        if run is None:
            logger.info(
                "airgap ingestion run %s no longer exists; dropping %s result",
                run_id,
                stage,
            )
            return

        run.worker_message_id = None

        if outcome["status"] != "succeeded":
            run.status = "FAILED"
            run.error_message = _best_failure_text(outcome)[:8000]
            run.completed_at = _now_naive()
            session.commit()
            return

        if stage == "mount":
            airgap_ingest_tick.process_mount_result(session, run, outcome)
        elif stage == "copy":
            airgap_ingest_tick.process_copy_result(session, run, outcome)
        else:
            logger.warning(
                "airgap_ingest result with unknown stage %r (run_id=%s); "
                "leaving row at %s",
                stage,
                run_id,
                run.status,
            )
        session.commit()
