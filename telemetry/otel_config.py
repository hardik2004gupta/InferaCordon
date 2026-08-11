"""
OpenTelemetry SDK configuration — OTLP/gRPC to Jaeger.

Per CLAUDE.md §18:
  Exporter:    OTLP gRPC to Jaeger port 4317
  Propagation: W3C TraceContext + Baggage
  Service name: ic-<service> (ic-gateway, ic-guardrail, ic-verifier)
  Span processor: BatchSpanProcessor with local buffering

Fail-open per CLAUDE.md §17 Failure Mode 9:
  If Jaeger is unreachable, spans buffer locally (BatchSpanProcessor)
  then drop after timeout. NEVER blocks inference serving.
"""
from __future__ import annotations

import logging

try:
    from opentelemetry import trace as _otel_trace
    _OTEL_AVAILABLE = True
except ImportError:
    _otel_trace = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False

log = logging.getLogger(__name__)


def configure_otel(service_name: str, otlp_endpoint: str) -> None:
    """
    Initialize OTel TracerProvider with OTLP/gRPC exporter pointing to Jaeger.
    Call once at application startup before first request.

    Fail-open: if setup fails (Jaeger unreachable, gRPC libs absent, etc.),
    logs a warning and leaves the default NoOpTracerProvider in place.
    The BatchSpanProcessor handles transient connectivity loss by buffering
    and eventually dropping spans — inference is never blocked.
    """
    try:
        from opentelemetry.baggage.propagation import W3CBaggagePropagator
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositeHTTPPropagator
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.resources import SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        resource = Resource.create({SERVICE_NAME: service_name})

        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=True,          # Jaeger all-in-one; no TLS in dev/staging
        )

        processor = BatchSpanProcessor(
            exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            export_timeout_millis=5_000,    # 5s export timeout per batch
            schedule_delay_millis=5_000,    # export every 5s when idle
        )

        provider = TracerProvider(resource=resource)
        provider.add_span_processor(processor)
        _otel_trace.set_tracer_provider(provider)

        # W3C TraceContext for traceparent/tracestate; Baggage for tenant metadata
        set_global_textmap(CompositeHTTPPropagator([
            TraceContextTextMapPropagator(),
            W3CBaggagePropagator(),
        ]))

        log.info("OTel configured: service=%s endpoint=%s", service_name, otlp_endpoint)

    except Exception as exc:
        log.warning(
            "OTel configuration failed — using NoOp tracer (telemetry disabled): %s", exc
        )
        # Default NoOpTracerProvider is already in place; nothing to do.


def get_tracer(name: str):
    """
    Return a named tracer from the global TracerProvider.
    Always returns a valid tracer — NoOp if configure_otel() was not called
    or failed. Returns a _NoOpTracer stub when opentelemetry is not installed.
    """
    if not _OTEL_AVAILABLE or _otel_trace is None:
        return _NoOpTracer()
    return _otel_trace.get_tracer(name)


class _NoOpSpan:
    """Minimal span stub used when opentelemetry is not installed."""
    def set_attribute(self, key: str, value: object) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _NoOpTracer:
    """Minimal tracer stub used when opentelemetry is not installed."""
    def start_span(self, name: str, **kwargs) -> _NoOpSpan:
        return _NoOpSpan()

    def start_as_current_span(self, name: str, **kwargs):
        return _NoOpSpan()
