"""Prometheus exposition endpoint for user-defined Custom Metrics.

This module exposes the LATEST successful sample of every user-defined custom
metric (Custom Metrics — Slice 1) as a Prometheus text-exposition endpoint
(``GET /metrics/custom-metrics``).  The existing Prometheus deployment — already
wired to Grafana via ``configure_prometheus_datasource`` — can scrape this
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
row — it logs and continues, returning HTTP 200 with whatever series are
available.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response

logger = logging.getLogger(__name__)

router = APIRouter()

# Prometheus text-exposition content type (format version 0.0.4).
PROM_CONTENT_TYPE = "text/plain; version=0.0.4"

METRIC_NAME = "sysmanage_custom_metric_value"
HELP_LINE = f"# HELP {METRIC_NAME} Latest value of a user-defined custom metric."
TYPE_LINE = f"# TYPE {METRIC_NAME} gauge"


def _escape_label_value(value) -> str:
    """Escape a string for use as a Prometheus label value.

    Per the exposition format only three characters must be escaped inside a
    label value: backslash (``\\`` -> ``\\\\``), double-quote (``"`` ->
    ``\\"``) and newline (``\\n`` -> ``\\n``).  Order matters — backslash is
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


def _collect_series_for_session(session, tenant_id):
    """Yield exposition lines for the latest-ok sample per (metric, host).

    For the given tenant DB session, select the LATEST ``status == "ok"``
    ``CustomMetricSample`` per ``(custom_metric_id, host_id)``, joined to the
    ``CustomMetric`` (name, unit) and the ``Host`` (fqdn).  Emits one gauge
    series per (metric, host).  Metrics with no ok sample are simply absent.

    ``tenant_id`` is included as a ``tenant`` label ONLY when it is not ``None``
    (i.e. only in multi-tenancy mode — the bootstrap/collapsed DB passes
    ``None`` and gets no tenant label).

    Never raises: any per-row problem is logged and that row is skipped.
    """
    # Late import to avoid an import cycle at module import time (models pull in
    # db, which pulls in config, etc.) — mirrors the other API modules.
    from backend.persistence.models import (  # noqa: PLC0415
        CustomMetric,
        CustomMetricSample,
        Host,
    )

    lines = []

    try:
        rows = (
            session.query(
                CustomMetric.name,
                CustomMetric.unit,
                Host.fqdn,
                CustomMetricSample.value,
                CustomMetricSample.custom_metric_id,
                CustomMetricSample.host_id,
                CustomMetricSample.collected_at,
            )
            .join(
                CustomMetric,
                CustomMetric.id == CustomMetricSample.custom_metric_id,
            )
            .join(Host, Host.id == CustomMetricSample.host_id)
            .filter(CustomMetricSample.status == "ok")
            .order_by(CustomMetricSample.collected_at.desc())
            .all()
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "custom-metric exporter: query FAILED for tenant_id=%s; "
            "skipping this database this scrape",
            tenant_id,
        )
        return lines

    # Keep only the latest ok sample per (metric_id, host_id).  Rows are ordered
    # newest-first, so the first one seen for a key is the latest.
    seen = set()
    for row in rows:
        try:
            key = (row.custom_metric_id, row.host_id)
            if key in seen:
                continue
            seen.add(key)

            if row.value is None:
                # An ok sample with a NULL value is not renderable; skip it.
                continue

            labels = [
                f'metric="{_escape_label_value(row.name)}"',
                f'host="{_escape_label_value(row.fqdn)}"',
                f'unit="{_escape_label_value(row.unit)}"',
            ]
            if tenant_id is not None:
                labels.append(f'tenant="{_escape_label_value(tenant_id)}"')

            lines.append(
                f"{METRIC_NAME}{{{','.join(labels)}}} " f"{_format_value(row.value)}"
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "custom-metric exporter: failed to render a sample row for "
                "tenant_id=%s; skipping the row",
                tenant_id,
            )
            continue

    return lines


def _render_exposition() -> str:
    """Build the full Prometheus exposition body across every provisioned DB.

    Walks ``iter_host_databases()`` — the shared per-tenant iteration seam also
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
    from backend.persistence.partitions import (  # noqa: PLC0415
        iter_host_databases,
    )

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
            except Exception:  # pylint: disable=broad-except
                pass

    # Header printed once; series follow.  Trailing newline is required by the
    # exposition format.
    out = [HELP_LINE, TYPE_LINE]
    out.extend(body_lines)
    return "\n".join(out) + "\n"


@router.get("/metrics/custom-metrics")
async def custom_metrics_exposition() -> Response:
    """Prometheus text-exposition of the latest ok custom-metric values.

    UNAUTHENTICATED (Prometheus-scrape convention) — see the module docstring:
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
