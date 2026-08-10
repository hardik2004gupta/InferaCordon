"""
Request tracing context: UUID request ID + W3C traceparent header.

Per CLAUDE.md Section 18 and Section 6 Step 3:
- Generate UUID-based request_id at gateway ingress (or preserve client-supplied one)
- Propagate W3C traceparent header to all downstream service calls
- Full OpenTelemetry span instrumentation belongs to Phase 9

File name: trace_context.py (per Part IX — authoritative over trace_injector.py from Component 1)
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

# W3C traceparent validation pattern
# version-trace_id-parent_id-trace_flags
_TRACEPARENT_RE = re.compile(
    r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
)

_REQUEST_ID_PREFIX = "req_"


@dataclass
class TraceContext:
    """
    Per-request trace context. Created once at gateway ingress; propagated unchanged.
    Must NOT be shared between requests.
    """
    request_id: str
    traceparent: Optional[str]
    tenant_id: str
    span: object = field(default=None, repr=False)  # opentelemetry.trace.Span (Phase 9)


def generate_request_id() -> str:
    """Generate a new request ID with the documented prefix."""
    return f"{_REQUEST_ID_PREFIX}{uuid.uuid4().hex[:12]}"


def create_trace_context(request: object, tenant_id: str) -> TraceContext:
    """
    Extract or create a TraceContext for an incoming request.

    Per CLAUDE.md Section 6 Step 3:
      "A UUID request ID is generated. A W3C traceparent header is constructed
       from this ID and attached to the request state."

    Args:
        request: FastAPI Request object (duck-typed to avoid hard import in tests).
        tenant_id: Already-resolved tenant identity from auth step.

    Returns:
        TraceContext with a unique, non-empty request_id.
    """
    # Allow client to supply a pre-existing request ID (useful for idempotency)
    client_id: str = getattr(
        getattr(request, "headers", None), "get", lambda *a, **k: ""
    )("X-Request-ID", "")

    if client_id and _is_safe_request_id(client_id):
        request_id = client_id
    else:
        request_id = generate_request_id()

    # Preserve incoming W3C traceparent if valid (distributed tracing context)
    incoming_traceparent: str = getattr(
        getattr(request, "headers", None), "get", lambda *a, **k: ""
    )("traceparent", "")

    traceparent: Optional[str] = None
    if incoming_traceparent and _TRACEPARENT_RE.match(incoming_traceparent):
        traceparent = incoming_traceparent

    return TraceContext(
        request_id=request_id,
        traceparent=traceparent,
        tenant_id=tenant_id,
    )


def inject_traceparent(headers: dict, ctx: TraceContext) -> dict:
    """
    Add W3C traceparent and X-Request-ID headers to an outbound request dict.
    Per CLAUDE.md Section 18.

    Returns the headers dict (mutated in-place for convenience).
    """
    headers["X-Request-ID"] = ctx.request_id
    if ctx.traceparent:
        headers["traceparent"] = ctx.traceparent
    return headers


def _is_safe_request_id(request_id: str) -> bool:
    """
    Validate a client-supplied request ID for safety.
    Allow alphanumeric, hyphens, underscores. Max 128 chars.
    Reject anything that could be used for log injection.
    """
    if not request_id or len(request_id) > 128:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_\-]+$", request_id))
