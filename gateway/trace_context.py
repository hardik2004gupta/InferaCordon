"""
Request tracing context: UUID request ID + W3C traceparent header.

Per CLAUDE.md Section 18 (OpenTelemetry):
- Generate UUID v4 request_id at gateway ingress
- Propagate W3C traceparent across all service calls
- Attach span attributes: tenant_id, domain, budget_class, cache_hit, etc.
- All trace data flows to Jaeger via OTLP (port 4317)

File name: trace_context.py (per Part IX — authoritative over trace_injector.py from Component 1)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class TraceContext:
    request_id: str
    traceparent: Optional[str]
    tenant_id: str
    span: object = None  # opentelemetry.trace.Span


def create_trace_context(request, tenant_id: str) -> TraceContext:
    """
    Extract or create W3C traceparent, generate request_id, start root span.
    """
    raise NotImplementedError("Implement per CLAUDE.md Section 18 (Week 1)")


def inject_traceparent(headers: dict, ctx: TraceContext) -> dict:
    """Add traceparent header for outbound requests to downstream services."""
    raise NotImplementedError("Implement per CLAUDE.md Section 18 (Week 1)")
