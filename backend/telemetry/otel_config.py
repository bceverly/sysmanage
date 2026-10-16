# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
OpenTelemetry configuration and setup for SysManage.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Core telemetry: the API, SDK, instrumentation and the Prometheus exporter.
# These are all pure-Python and ship everywhere.
try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from prometheus_client import start_http_server

    TELEMETRY_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "OpenTelemetry dependencies not available: %s. Telemetry will be disabled.",
        e,
    )
    TELEMETRY_AVAILABLE = False
    # Define stub objects so the code doesn't break
    metrics = None  # type: ignore[assignment]
    trace = None  # type: ignore[assignment]

# The OTLP exporters are a SEPARATE optional dependency, imported on their own.
#
# They come from opentelemetry-exporter-otlp, which pulls grpcio -- a compiled
# package with no build on some platforms.  The OpenBSD port deliberately omits
# it (see installer/openbsd/build-libs.sh).  Previously these two imports sat in
# the same try block as everything above, so one missing optional exporter
# disabled the ENTIRE telemetry stack: Prometheus metrics and all FastAPI /
# SQLAlchemy / requests / logging instrumentation went dark too, even though
# those packages were installed and working.  Splitting the import means losing
# OTLP costs exactly OTLP.
try:
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    OTLP_AVAILABLE = True
except ImportError as e:
    logger.info(
        "OTLP exporters not available (%s). Prometheus metrics and instrumentation "
        "are unaffected; only OTLP export is disabled.",
        e,
    )
    OTLP_AVAILABLE = False
    OTLPMetricExporter = None  # type: ignore[assignment,misc]
    OTLPSpanExporter = None  # type: ignore[assignment,misc]

# Global state for telemetry
_telemetry_enabled = False
_prometheus_server_started = False


_TRUE = ("true", "1", "yes", "on")


def _telemetry_config() -> dict:
    """The ``telemetry:`` section of sysmanage.yaml ({} when absent or unreadable)."""
    try:
        from backend.config import config  # pylint: disable=import-outside-toplevel

        section = config.get_config().get("telemetry") or {}
        return section if isinstance(section, dict) else {}
    except Exception:  # pylint: disable=broad-except
        return {}


def is_telemetry_enabled() -> bool:
    """Telemetry is OFF unless asked for (2026-10-15).

    It used to default ON: a fresh install then exported every few seconds to
    a collector at localhost:4317 that nobody had installed (an ERROR line each
    time) and opened a Prometheus endpoint on 0.0.0.0:9090 -- a second network
    listener beside nginx.  Now: ``OTEL_ENABLED`` (environment, wins when set)
    or ``telemetry.enabled`` in sysmanage.yaml.
    """
    if not TELEMETRY_AVAILABLE:
        return False
    override = os.getenv("OTEL_ENABLED")
    if override is not None:
        return override.strip().lower() in _TRUE
    return bool(_telemetry_config().get("enabled", False))


def telemetry_settings() -> dict:
    """Where telemetry goes when it is on: the OTLP endpoint (None = no OTLP
    export -- never an assumed localhost collector) and the Prometheus
    endpoint's address and port (loopback by default; scrape it through
    nginx or a local agent, or set ``prometheus_addr`` to expose it).
    Environment variables win over sysmanage.yaml."""
    section = _telemetry_config()
    return {
        "otlp_endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or section.get("otlp_endpoint")
        or None,
        "prometheus_addr": os.getenv("OTEL_PROMETHEUS_ADDR")
        or section.get("prometheus_addr")
        or "127.0.0.1",
        "prometheus_port": int(
            os.getenv("OTEL_PROMETHEUS_PORT") or section.get("prometheus_port") or 9090
        ),
    }


def setup_telemetry(
    app,
    service_name: str = "sysmanage",
    service_version: str = "1.0.0",
    otlp_endpoint: Optional[str] = None,
    prometheus_port: int = 9090,
    prometheus_addr: str = "127.0.0.1",
) -> None:
    """
    Set up OpenTelemetry instrumentation for the application.

    Args:
        app: The FastAPI application instance
        service_name: Name of the service for telemetry
        service_version: Version of the service
        otlp_endpoint: OTLP collector endpoint (e.g., "http://localhost:4317")
        prometheus_port: Port for Prometheus metrics endpoint
    """
    global _telemetry_enabled  # pylint: disable=global-statement

    # Check if telemetry should be enabled
    if not is_telemetry_enabled():
        logger.info(
            "OpenTelemetry is off (the default). Set OTEL_ENABLED=true or "
            "telemetry.enabled: true in sysmanage.yaml to turn it on."
        )
        return

    try:
        logger.info("Setting up OpenTelemetry instrumentation...")

        # Create resource with service information
        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                SERVICE_VERSION: service_version,
            }
        )

        # Set up tracing
        setup_tracing(resource, otlp_endpoint)

        # Set up metrics
        setup_metrics(resource, otlp_endpoint, prometheus_port, prometheus_addr)

        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumented for OpenTelemetry")

        # Instrument SQLAlchemy (will be applied when engines are created)
        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemy instrumented for OpenTelemetry")

        # Instrument requests library
        RequestsInstrumentor().instrument()
        logger.info("Requests library instrumented for OpenTelemetry")

        # Instrument logging
        LoggingInstrumentor().instrument()
        logger.info("Logging instrumented for OpenTelemetry")

        _telemetry_enabled = True
        logger.info("OpenTelemetry setup completed successfully")

    except Exception as e:  # pylint: disable=broad-except
        logger.exception("Failed to set up OpenTelemetry: %s", e, exc_info=True)
        # Don't fail the application if telemetry setup fails
        _telemetry_enabled = False


def setup_tracing(resource: Resource, otlp_endpoint: Optional[str] = None) -> None:
    """
    Set up OpenTelemetry tracing.

    Args:
        resource: The resource describing this service
        otlp_endpoint: OTLP collector endpoint for traces
    """
    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Add OTLP exporter if endpoint is provided and the exporter is installed
    if otlp_endpoint and not OTLP_AVAILABLE:
        logger.warning(
            "OTLP endpoint %s configured but the OTLP exporter is not installed; "
            "traces will not be exported. Tracing itself remains active.",
            otlp_endpoint,
        )
    elif otlp_endpoint:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            span_processor = BatchSpanProcessor(otlp_exporter)
            tracer_provider.add_span_processor(span_processor)
            logger.info("OTLP trace exporter configured for %s", otlp_endpoint)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Failed to configure OTLP trace exporter: %s", e)

    # Set the global tracer provider
    trace.set_tracer_provider(tracer_provider)
    logger.info("Tracing configured successfully")


def setup_metrics(
    resource: Resource,
    otlp_endpoint: Optional[str] = None,
    prometheus_port: int = 9090,
    prometheus_addr: str = "127.0.0.1",
) -> None:
    """
    Set up OpenTelemetry metrics with both OTLP and Prometheus exporters.

    Args:
        resource: The resource describing this service
        otlp_endpoint: OTLP collector endpoint for metrics
        prometheus_port: Port for Prometheus metrics HTTP server
    """
    global _prometheus_server_started  # pylint: disable=global-statement

    readers = []

    # Add Prometheus exporter
    try:
        prometheus_reader = PrometheusMetricReader()
        readers.append(prometheus_reader)

        # Start Prometheus HTTP server if not already started
        if not _prometheus_server_started:
            # Loopback by default: nginx is the only network listener.
            start_http_server(port=prometheus_port, addr=prometheus_addr)
            _prometheus_server_started = True
            logger.info(
                "Prometheus metrics server started on %s:%s",
                prometheus_addr,
                prometheus_port,
            )
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("Failed to set up Prometheus exporter: %s", e)

    # Add OTLP exporter if endpoint is provided and the exporter is installed
    if otlp_endpoint and not OTLP_AVAILABLE:
        logger.warning(
            "OTLP endpoint %s configured but the OTLP exporter is not installed; "
            "metrics will not be exported over OTLP. Prometheus metrics are "
            "unaffected.",
            otlp_endpoint,
        )
    elif otlp_endpoint:
        try:
            otlp_metric_exporter = OTLPMetricExporter(
                endpoint=otlp_endpoint, insecure=True
            )
            otlp_reader = PeriodicExportingMetricReader(
                otlp_metric_exporter,
                export_interval_millis=60000,  # Export every 60 seconds
            )
            readers.append(otlp_reader)
            logger.info("OTLP metric exporter configured for %s", otlp_endpoint)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Failed to configure OTLP metric exporter: %s", e)

    # Create meter provider with all configured readers
    if readers:
        meter_provider = MeterProvider(resource=resource, metric_readers=readers)
        metrics.set_meter_provider(meter_provider)
        logger.info("Metrics configured successfully")
    else:
        logger.warning("No metric exporters configured")


def get_tracer(name: str):
    """
    Get a tracer for creating spans.

    Args:
        name: The name of the tracer (usually __name__ of the calling module)

    Returns:
        A tracer instance or None if telemetry is not available
    """
    if not TELEMETRY_AVAILABLE or trace is None:
        return None
    return trace.get_tracer(name)


def get_meter(name: str):
    """
    Get a meter for creating metrics.

    Args:
        name: The name of the meter (usually __name__ of the calling module)

    Returns:
        A meter instance or None if telemetry is not available
    """
    if not TELEMETRY_AVAILABLE or metrics is None:
        return None
    return metrics.get_meter(name)
