"""
OpenTelemetry SDK configuration — Jaeger OTLP exporter.

Per CLAUDE.md Section 18:
- Service name: ic-<service> (ic-gateway, ic-guardrail, ic-verifier)
- Exporter: OTLP gRPC to Jaeger (port 4317)
- Propagation: W3C TraceContext + Baggage
- Instrumentation: FastAPI auto-instrumentation + httpx auto-instrumentation
- Span attributes: tenant_id, domain, budget_class, cache_hit, model_version
"""
from __future__ import annotations


def configure_otel(service_name: str, otlp_endpoint: str) -> None:
    """
    Initialize OpenTelemetry SDK with OTLP/gRPC exporter pointing to Jaeger.
    Call once at application startup before first request.
    """
    raise NotImplementedError("Implement per CLAUDE.md Section 18 (Week 1)")


def get_tracer(name: str) -> object:
    """Return a named tracer for span creation."""
    raise NotImplementedError("Implement per CLAUDE.md Section 18 (Week 1)")
