"""
OpenTelemetry configuration and setup for SysManage.
"""

import logging
import os
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server


logger = logging.getLogger(__name__)

# Global state for telemetry
_telemetry_enabled = False
_prometheus_server_started = False


def is_telemetry_enabled() -> bool:
    """
    Check if telemetry is enabled based on environment variable.
    Default is True (enabled) unless explicitly disabled.
    """
    return os.getenv("OTEL_ENABLED", "true").lower() in ("true", "1", "yes")


def setup_telemetry(
    app,
    service_name: str = "sysmanage",
    service_version: str = "1.0.0",
    otlp_endpoint: Optional[str] = None,
    prometheus_port: int = 9090,
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
        logger.info("OpenTelemetry is disabled. Remove OTEL_ENABLED=false to enable.")
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
        setup_metrics(resource, otlp_endpoint, prometheus_port)

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
        logger.error("Failed to set up OpenTelemetry: %s", e, exc_info=True)
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

    # Add OTLP exporter if endpoint is provided
    if otlp_endpoint:
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
    resource: Resource, otlp_endpoint: Optional[str] = None, prometheus_port: int = 9090
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
            start_http_server(port=prometheus_port, addr="0.0.0.0")
            _prometheus_server_started = True
            logger.info("Prometheus metrics server started on port %s", prometheus_port)
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("Failed to set up Prometheus exporter: %s", e)

    # Add OTLP exporter if endpoint is provided
    if otlp_endpoint:
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
        A tracer instance
    """
    if not _telemetry_enabled:
        return trace.get_tracer(name)
    return trace.get_tracer(name)


def get_meter(name: str):
    """
    Get a meter for creating metrics.

    Args:
        name: The name of the meter (usually __name__ of the calling module)

    Returns:
        A meter instance
    """
    if not _telemetry_enabled:
        return metrics.get_meter(name)
    return metrics.get_meter(name)
