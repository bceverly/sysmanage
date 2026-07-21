# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content-lifecycle engine-path result-apply handlers (Phase 16).

Extracted from ``backend.services.proplus_dispatch`` to keep that module under
pylint's max-module-lines cap; re-imported there and registered in
``_SIMPLE_RESULT_HANDLERS`` under ``"content_lifecycle_op"``.

These handlers translate a completed ``content_lifecycle_engine`` publish plan
``outcome`` into a ``SharedContentViewVersion`` row update.  Unlike the
repository-mirroring handlers (which write the TENANT ``mirror_repository``),
content-view versions live in the SHARED partition, so we acquire a
``shared_sessionmaker()`` session rather than the default request session.

A couple of dispatch primitives (``_now_naive``, ``_best_failure_text``) live in
``proplus_dispatch`` and are imported lazily to avoid a circular import at load.
"""

import logging
from typing import Any, Dict

from backend.persistence import models
from backend.persistence.models.content_lifecycle import CVV_FAILED, CVV_PUBLISHED
from backend.persistence.partitions import shared_sessionmaker

logger = logging.getLogger(__name__)


def _publish_manifest(outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Compact record stored on the published version's ``manifest`` column.

    The per-file SHA manifest is materialized on the mirror host; here we keep a
    lightweight summary (command count + terminal status) so the UI/audit can
    show what ran without hauling the full file list back over the wire.
    """
    commands = outcome.get("commands") or []
    return {
        "command_count": len(commands),
        "outcome_status": outcome.get("status"),
    }


def _apply_content_lifecycle_op_result(
    primary_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Handle completion of a ``content_lifecycle_engine`` plan.

    ``primary_id`` is ``"<action>:<cvv_id>"``.  Only ``publish_materialize`` is
    defined today: stamp the ``SharedContentViewVersion`` published/failed.
    """
    if ":" not in primary_id:
        action, cvv_id = primary_id, ""
    else:
        action, cvv_id = primary_id.split(":", 1)

    if action != "publish_materialize" or not cvv_id:
        # Never silently drop an unroutable result — log it with context.
        logger.warning(
            "content_lifecycle result: unhandled primary_id %r (host %s)",
            primary_id,
            host_id,
        )
        return

    from backend.services.proplus_dispatch import _best_failure_text, _now_naive

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
            row.manifest = _publish_manifest(outcome)
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
