# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Prometheus exposition endpoint for user-defined Custom Metrics.

This module exposes the LATEST successful sample of every user-defined custom
metric (Custom Metrics -- Slice 1) as a Prometheus text-exposition endpoint
(``GET /metrics/custom-metrics``).  The existing Prometheus deployment -- already
wired to Grafana via ``configure_prometheus_datasource`` -- can scrape this
endpoint so custom-metric values flow through to Grafana dashboards.  This is
"approach B": rather than push into Grafana, we surface the samples in a format
the existing Prometheus already knows how to pull, hand-rendering the text
format so NO new pip dependency (``prometheus_client``) is required.

SECURITY / NETWORK NOTE
-----------------------
This endpoint is UNAUTHENTICATED, following the Prometheus-scrape convention
(scrapers do not present a JWT).  It EXPOSES metric VALUES and host FQDNs.  It
MUST be network-restricted / firewalled so that only the Prometheus host can
reach it (e.g. bind/allow only the Prometheus scraper's address, or place it
behind a reverse-proxy allow-list).  Do not expose it to the public internet.

A scrape must ALWAYS succeed: this handler never raises on a bad tenant or a bad
row -- it logs and continues, returning HTTP 200 with whatever series are
available.
"""

from __future__ import annotations

import logging

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Response
from sqlalchemy import and_, func

logger = logging.getLogger(__name__)

router = APIRouter()

# Prometheus text-exposition content type (format version 0.0.4).
PROM_CONTENT_TYPE = "text/plain; version=0.0.4"

METRIC_NAME = "sysmanage_custom_metric_value"
HELP_LINE = f"# HELP {METRIC_NAME} Latest value of a custom or built-in host metric."
TYPE_LINE = f"# TYPE {METRIC_NAME} gauge"


def _escape_label_value(value) -> str:
    """Escape a string for use as a Prometheus label value.

    Per the exposition format only three characters must be escaped inside a
    label value: backslash (``\\`` -> ``\\\\``), double-quote (``"`` ->
    ``\\"``) and newline (``\\n`` -> ``\\n``).  Order matters -- backslash is
    escaped FIRST so we don't double-escape the backslashes we introduce.
    """
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "\\n")
    return text


def _format_value(value) -> str:
    """Render a float sample value for the exposition line."""
    # repr on a float round-trips; Prometheus accepts standard float text.
    return repr(float(value))


# A sample older than this many cadences is not a CURRENT value: exporting it
# would keep a dead host's last reading in Grafana forever.  The floor keeps a
# short-cadence metric from vanishing over one late report.
_FRESH_CADENCES = 2
_FRESH_FLOOR = timedelta(hours=1)


def _latest_ok_samples(session, metric, now, sample_model, host_model):
    """``[(fqdn, value)]`` -- each host's latest ok sample of ``metric``, if
    it is recent.

    Asked of the database, one metric at a time and bounded by time, so a
    scrape reads a few rows per host through the (metric, host, collected_at)
    index.  (It used to load every ok sample ever stored and keep the newest
    in Python -- tolerable for a handful of script metrics, but the built-in
    series add ~480,000 rows a day per 1,000 hosts.)
    """
    cadence = timedelta(seconds=metric.cadence_seconds or 0) * _FRESH_CADENCES
    cutoff = now - max(cadence, _FRESH_FLOOR)
    latest = (
        session.query(
            sample_model.host_id.label("host_id"),
            func.max(sample_model.collected_at).label("at"),
        )
        .filter(
            sample_model.custom_metric_id == metric.id,
            sample_model.status == "ok",
            sample_model.collected_at >= cutoff,
        )
        .group_by(sample_model.host_id)
        .subquery()
    )
    return (
        session.query(host_model.fqdn, sample_model.value)
        .join(
            latest,
            and_(
                sample_model.host_id == latest.c.host_id,
                sample_model.collected_at == latest.c.at,
            ),
        )
        .join(host_model, host_model.id == sample_model.host_id)
        .filter(
            sample_model.custom_metric_id == metric.id,
            sample_model.status == "ok",
        )
        .all()
    )


def _render_line(metric, fqdn, value, tenant_id):
    """One exposition line, or ``None`` for a sample that cannot be rendered."""
    if value is None:
        # An ok sample with a NULL value is not renderable; skip it.
        return None
    try:
        labels = [
            f'metric="{_escape_label_value(metric.name)}"',
            f'host="{_escape_label_value(fqdn)}"',
            f'unit="{_escape_label_value(metric.unit)}"',
            # Phase 21.5: lets a Grafana query pick out the built-in host
            # series (CPU, memory, ...) from operator-defined metrics.
            f'builtin="{"true" if metric.builtin_key else "false"}"',
        ]
        if tenant_id is not None:
            labels.append(f'tenant="{_escape_label_value(tenant_id)}"')
        return f"{METRIC_NAME}{{{','.join(labels)}}} {_format_value(value)}"
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "custom-metric exporter: failed to render a sample row for "
            "tenant_id=%s; skipping the row",
            tenant_id,
        )
        return None


def _collect_series_for_session(session, tenant_id):
    """Yield exposition lines for the latest-ok sample per (metric, host).

    For the given tenant DB session, select the LATEST ``status == "ok"``
    ``CustomMetricSample`` per ``(custom_metric_id, host_id)``, joined to the
    ``CustomMetric`` (name, unit) and the ``Host`` (fqdn).  Emits one gauge
    series per (metric, host).  Metrics with no ok sample are simply absent.

    ``tenant_id`` is included as a ``tenant`` label ONLY when it is not ``None``
    (i.e. only in multi-tenancy mode -- the bootstrap/collapsed DB passes
    ``None`` and gets no tenant label).

    Never raises: any per-row problem is logged and that row is skipped.
    """
    # Late import to avoid an import cycle at module import time (models pull in
    # db, which pulls in config, etc.) -- mirrors the other API modules.
    from backend.persistence.models import (
        CustomMetric,  # noqa: PLC0415
        CustomMetricSample,
        Host,
    )

    lines = []
    now = datetime.now(timezone.utc)

    try:
        metrics = session.query(CustomMetric).all()
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "custom-metric exporter: query FAILED for tenant_id=%s; "
            "skipping this database this scrape",
            tenant_id,
        )
        return lines

    for metric in metrics:
        try:
            rows = _latest_ok_samples(session, metric, now, CustomMetricSample, Host)
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "custom-metric exporter: sample query FAILED for metric %s, "
                "tenant_id=%s; skipping the metric this scrape",
                metric.id,
                tenant_id,
            )
            continue
        for fqdn, value in rows:
            line = _render_line(metric, fqdn, value, tenant_id)
            if line is not None:
                lines.append(line)

    return lines


def _render_exposition() -> str:
    """Build the full Prometheus exposition body across every provisioned DB.

    Walks ``iter_host_databases()`` -- the shared per-tenant iteration seam also
    used by the custom-metric retention service.  In single-tenant /
    ``multitenancy.enabled`` false (collapsed) mode it yields ONLY the one
    bootstrap/main database (``tenant_id`` = ``None`` → no ``tenant`` label); in
    multi-tenancy mode it yields the bootstrap DB plus every provisioned tenant
    DB, each tagged with its ``tenant`` id.

    The ``# HELP``/``# TYPE`` header is printed exactly once, ahead of all
    series.  A bad tenant/session is logged and skipped so a scrape always
    returns a usable body.
    """
    # Late import: partitions -> models -> ... import cycle guard, matching the
    # retention service.
    from backend.persistence.partitions import iter_host_databases  # noqa: PLC0415

    body_lines = []

    for label, tenant_id, session in iter_host_databases():
        try:
            body_lines.extend(_collect_series_for_session(session, tenant_id))
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "custom-metric exporter: collecting series FAILED for %s "
                "(tenant_id=%s); skipping it this scrape",
                label,
                tenant_id,
            )
        finally:
            # iter_host_databases hands us ownership of every session it opens.
            try:
                session.close()
            except Exception:  # nosec B110  # pylint: disable=broad-except
                pass

    # Header printed once; series follow.  Trailing newline is required by the
    # exposition format.
    out = [HELP_LINE, TYPE_LINE]
    out.extend(body_lines)
    return "\n".join(out) + "\n"


@router.get("/metrics/custom-metrics")
async def custom_metrics_exposition() -> Response:
    """Prometheus text-exposition of the latest ok custom-metric values.

    UNAUTHENTICATED (Prometheus-scrape convention) -- see the module docstring:
    this endpoint should be firewalled to the Prometheus host.  Always returns
    HTTP 200 with a ``text/plain; version=0.0.4`` body; never raises on a bad
    tenant/row (logged and skipped) so a scrape never fails.
    """
    try:
        body = _render_exposition()
    except Exception:  # pylint: disable=broad-except
        # Absolute backstop: a scrape must still get a valid (if empty) body.
        logger.exception(
            "custom-metric exporter: unexpected error building the exposition; "
            "returning header-only body"
        )
        body = HELP_LINE + "\n" + TYPE_LINE + "\n"

    return Response(content=body, media_type=PROM_CONTENT_TYPE)
