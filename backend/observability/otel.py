"""OpenTelemetry Integration.

Phase I: Observability + evaluation using OpenTelemetry for distributed tracing.
"""

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


class ButlerOpenTelemetry:
    """OpenTelemetry configuration for Butler observability.

    This class:
    - Configures OpenTelemetry tracing
    - Sets up OTLP exporters
    - Instruments FastAPI and HTTP clients
    - Provides tracing context
    """

    def __init__(self, service_name: str = "butler-backend", otlp_endpoint: str | None = None):
        """Initialize OpenTelemetry configuration.

        Args:
            service_name: Service name for tracing
            otlp_endpoint: OTLP collector endpoint
        """
        self._service_name = service_name
        self._otlp_endpoint = otlp_endpoint
        self._tracer_provider = None

    def initialize(self) -> None:
        """Initialize OpenTelemetry tracing."""
        resource = Resource.create({"service.name": self._service_name})

        self._tracer_provider = TracerProvider(resource=resource)

        # Configure OTLP exporter
        if self._otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=self._otlp_endpoint, insecure=True)
            self._tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("otel_exporter_configured", endpoint=self._otlp_endpoint)
        else:
            logger.warning("otel_no_endpoint_configured")

        # Set global tracer provider
        trace.set_tracer_provider(self._tracer_provider)
        logger.info("otel_initialized", service_name=self._service_name)

    def instrument_fastapi(self, app: Any) -> None:
        """Instrument FastAPI application.

        Args:
            app: FastAPI application
        """
        try:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("fastapi_instrumented")
        except Exception as e:
            logger.exception("fastapi_instrumentation_failed")

    def instrument_httpx(self) -> None:
        """Instrument HTTPX client."""
        try:
            HTTPXClientInstrumentor().instrument()
            logger.info("httpx_instrumented")
        except Exception as e:
            logger.exception("httpx_instrumentation_failed")

    def get_tracer(self, name: str) -> Any:
        """Get a tracer instance.

        Args:
            name: Tracer name

        Returns:
            Tracer instance
        """
        return trace.get_tracer(name)

    def shutdown(self) -> None:
        """Shutdown OpenTelemetry tracing."""
        if self._tracer_provider:
            self._tracer_provider.shutdown()
            logger.info("otel_shutdown")
