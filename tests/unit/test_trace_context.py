"""
Unit tests for gateway/trace_context.py.

Tests cover:
- generate_request_id: format, uniqueness, prefix
- _is_safe_request_id: allow/reject patterns
- create_trace_context: client-supplied ID, generated ID, traceparent propagation
- inject_traceparent: header injection
"""
from __future__ import annotations

import re

import pytest

from gateway.trace_context import (
    TraceContext,
    _is_safe_request_id,
    create_trace_context,
    generate_request_id,
    inject_traceparent,
)

_REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{12}$")
_TRACEPARENT_VALID = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class TestGenerateRequestId:
    def test_format(self):
        rid = generate_request_id()
        assert _REQUEST_ID_PATTERN.match(rid), f"Bad format: {rid!r}"

    def test_uniqueness(self):
        ids = {generate_request_id() for _ in range(1000)}
        assert len(ids) == 1000

    def test_prefix(self):
        assert generate_request_id().startswith("req_")


class TestIsSafeRequestId:
    def test_valid_generated_id(self):
        rid = generate_request_id()
        assert _is_safe_request_id(rid)

    def test_valid_custom_alphanumeric(self):
        assert _is_safe_request_id("my-request-123_abc")

    def test_empty_string_rejected(self):
        assert not _is_safe_request_id("")

    def test_too_long_rejected(self):
        assert not _is_safe_request_id("a" * 129)

    def test_exactly_128_accepted(self):
        assert _is_safe_request_id("a" * 128)

    def test_newline_rejected(self):
        assert not _is_safe_request_id("req_\ninjection")

    def test_space_rejected(self):
        assert not _is_safe_request_id("req_ bad")

    def test_semicolon_rejected(self):
        assert not _is_safe_request_id("req_abc;DROP")

    def test_dot_rejected(self):
        assert not _is_safe_request_id("req.abc")

    def test_slash_rejected(self):
        assert not _is_safe_request_id("req/abc")


class _MockHeaders:
    """Minimal dict-like headers object."""
    def __init__(self, data: dict):
        self._data = {k.lower(): v for k, v in data.items()}

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key.lower(), default)


class _MockRequest:
    def __init__(self, headers: dict):
        self.headers = _MockHeaders(headers)


class TestCreateTraceContext:
    def test_generates_request_id_when_no_client_id(self):
        req = _MockRequest({})
        ctx = create_trace_context(req, "acme_corp")
        assert _REQUEST_ID_PATTERN.match(ctx.request_id)

    def test_accepts_valid_client_request_id(self):
        req = _MockRequest({"X-Request-ID": "client-supplied-id-123"})
        ctx = create_trace_context(req, "acme_corp")
        assert ctx.request_id == "client-supplied-id-123"

    def test_rejects_unsafe_client_request_id(self):
        req = _MockRequest({"X-Request-ID": "bad id with spaces"})
        ctx = create_trace_context(req, "acme_corp")
        # Falls back to generated ID
        assert _REQUEST_ID_PATTERN.match(ctx.request_id)

    def test_propagates_valid_traceparent(self):
        req = _MockRequest({"traceparent": _TRACEPARENT_VALID})
        ctx = create_trace_context(req, "acme_corp")
        assert ctx.traceparent == _TRACEPARENT_VALID

    def test_drops_invalid_traceparent(self):
        req = _MockRequest({"traceparent": "not-a-valid-traceparent"})
        ctx = create_trace_context(req, "acme_corp")
        assert ctx.traceparent is None

    def test_no_traceparent_when_header_absent(self):
        req = _MockRequest({})
        ctx = create_trace_context(req, "acme_corp")
        assert ctx.traceparent is None

    def test_tenant_id_stored(self):
        req = _MockRequest({})
        ctx = create_trace_context(req, "acme_corp")
        assert ctx.tenant_id == "acme_corp"

    def test_span_defaults_to_none(self):
        req = _MockRequest({})
        ctx = create_trace_context(req, "acme_corp")
        assert ctx.span is None

    def test_two_requests_get_different_ids(self):
        req = _MockRequest({})
        ctx1 = create_trace_context(req, "t1")
        ctx2 = create_trace_context(req, "t2")
        assert ctx1.request_id != ctx2.request_id

    def test_traceparent_wrong_length_dropped(self):
        # Wrong trace_id length (should be 32 hex chars)
        short = "00-abc-00f067aa0ba902b7-01"
        req = _MockRequest({"traceparent": short})
        ctx = create_trace_context(req, "t")
        assert ctx.traceparent is None


class TestInjectTraceparent:
    def test_injects_request_id(self):
        ctx = TraceContext(request_id="req_abc", traceparent=None, tenant_id="t")
        headers = inject_traceparent({}, ctx)
        assert headers["X-Request-ID"] == "req_abc"

    def test_injects_traceparent_when_present(self):
        ctx = TraceContext(request_id="req_abc", traceparent=_TRACEPARENT_VALID, tenant_id="t")
        headers = inject_traceparent({}, ctx)
        assert headers["traceparent"] == _TRACEPARENT_VALID

    def test_no_traceparent_key_when_absent(self):
        ctx = TraceContext(request_id="req_abc", traceparent=None, tenant_id="t")
        headers = inject_traceparent({}, ctx)
        assert "traceparent" not in headers

    def test_mutates_and_returns_dict(self):
        ctx = TraceContext(request_id="req_abc", traceparent=None, tenant_id="t")
        original: dict = {"existing": "value"}
        returned = inject_traceparent(original, ctx)
        assert returned is original
        assert "existing" in returned
