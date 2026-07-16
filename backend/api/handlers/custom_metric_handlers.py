# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Custom Metric sample ingest handler (Custom Metrics & Graphs — Slice 3b).

Consumes the agent's ``custom_metric_samples`` data message and stores each
sample as a ``custom_metric_sample`` row in the bound host's tenant database.

This is purely mechanical STORAGE into an OSS table — the metric DEFINITION,
targeting, scheduling and any graphing/alerting LOGIC live in the licensed
``observability_engine`` (Pro+).  Nothing here touches licensed logic.

``db`` is the caller's session, already tenant-routed to the bound host's
database (the caller owns the session lifecycle).  Following the sibling
convention (e.g. ``handle_gpg_key_command_result`` / ``handle_user_access_update``),
this handler resolves the host from ``connection.host_id`` and commits its own
transaction.

Contract (from the agent):
    message_type = "custom_metric_samples"
    data payload = {
        "samples": [
            {"metric_id", "value", "status", "error_detail", "collected_at"},
            ...
        ]
    }
``value`` may be null when ``status == "error"``; ``collected_at`` is ISO-8601
UTC (falls back to server now() when missing/unparseable).

NOTE (follow-up, NOT in scope here): ``custom_metric_sample`` grows without
bound — a retention/prune of old rows is required and is deferred to a later
slice.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.persistence.models.custom_metric import (
    SAMPLE_STATUS_ERROR,
    SAMPLE_STATUS_OK,
    CustomMetric,
    CustomMetricSample,
)

logger = logging.getLogger(__name__)


def _parse_collected_at(raw: Any) -> datetime:
    """Parse an ISO-8601 UTC ``collected_at`` string, falling back to server
    now() when missing or unparseable.  Always returns a timezone-aware UTC
    datetime."""
    if isinstance(raw, str) and raw:
        candidate = raw.strip()
        # Accept a trailing "Z" (Zulu) which ``fromisoformat`` rejects on
        # older CPython.
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


async def handle_custom_metric_samples(  # NOSONAR
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Ingest a batch of custom-metric samples into ``custom_metric_sample``.

    Host is resolved from ``connection.host_id`` (sibling convention).  Each
    sample's ``metric_id`` is validated against the ``CustomMetric`` table in
    this tenant DB; unknown metric_ids are skipped (debug log).  Samples are
    batch-inserted and committed once.  If the whole batch is dropped, a loud
    warning (host_id + counts only — never raw script values) is logged per the
    log-loudly convention.  Missing host / empty batch are handled gracefully —
    we never raise."""
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "custom_metric_samples received but connection has no host_id; ignoring"
        )
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": "Host not registered",
            "data": {},
        }

    samples = message_data.get("samples")
    if not isinstance(samples, list):
        samples = message_data.get("data", {}).get("samples")
    if not isinstance(samples, list):
        samples = []

    received = len(samples)
    if received == 0:
        logger.debug(
            "custom_metric_samples for host %s carried no samples; nothing to store",
            host_id,
        )
        return {"message_type": "custom_metric_samples_ack"}

    try:
        # Resolve which metric_ids are valid CustomMetrics in this tenant DB.
        raw_ids = {
            s.get("metric_id")
            for s in samples
            if isinstance(s, dict) and s.get("metric_id")
        }
        # ``metric_id`` arrives as a string; ``CustomMetric.id`` is a GUID
        # (UUID on the Python side).  Compare via string form so set membership
        # is not defeated by str-vs-UUID identity.
        known_ids = set()
        if raw_ids:
            known_ids = {
                str(row.id)
                for row in db.query(CustomMetric.id)
                .filter(CustomMetric.id.in_(raw_ids))
                .all()
            }

        rows = []
        skipped_unknown = 0
        for sample in samples:
            if not isinstance(sample, dict):
                skipped_unknown += 1
                continue
            metric_id = sample.get("metric_id")
            if metric_id is None or str(metric_id) not in known_ids:
                # Unknown metric_id (deleted metric, wrong tenant, etc.) — skip.
                logger.debug(
                    "custom_metric_samples: skipping unknown metric_id for host %s",
                    host_id,
                )
                skipped_unknown += 1
                continue

            status = sample.get("status") or SAMPLE_STATUS_OK
            # An errored sample never stores a value, regardless of what was sent.
            if status == SAMPLE_STATUS_ERROR:
                value = None
            else:
                value = sample.get("value")

            rows.append(
                CustomMetricSample(
                    custom_metric_id=metric_id,
                    host_id=host_id,
                    value=value,
                    status=status,
                    error_detail=sample.get("error_detail"),
                    collected_at=_parse_collected_at(sample.get("collected_at")),
                )
            )

        stored = len(rows)
        if stored == 0:
            # Whole batch dropped — log loudly (counts only, never raw values).
            logger.warning(
                "custom_metric_samples for host %s dropped ENTIRELY: "
                "received=%s stored=0 skipped_unknown=%s",
                host_id,
                received,
                skipped_unknown,
            )
            return {"message_type": "custom_metric_samples_ack"}

        db.bulk_save_objects(rows)
        db.commit()

        if skipped_unknown:
            logger.info(
                "custom_metric_samples for host %s: stored=%s skipped_unknown=%s",
                host_id,
                stored,
                skipped_unknown,
            )
        else:
            logger.debug(
                "custom_metric_samples for host %s: stored=%s", host_id, stored
            )

        return {"message_type": "custom_metric_samples_ack"}

    except Exception as exc:  # pylint: disable=broad-exception-caught
        db.rollback()
        logger.exception(
            "Error storing custom_metric_samples for host %s (received=%s): %s",
            host_id,
            received,
            exc,
        )
        return {
            "message_type": "error",
            "error_type": "custom_metric_samples_error",
            "message": "Failed to store custom metric samples",
            "data": {},
        }
